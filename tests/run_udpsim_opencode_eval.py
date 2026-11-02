"""Brokered OpenCode proxy QA. Raw inputs/results stay under ignored out/."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/udpsim-opencode-qa'
SKILL = ROOT / 'skills/udpsim-icd-authoring'
MODELS = ('flint-40b-free', 'nemotron-3.5-lightning-free', 'glm-5.3-flash-free')
CORE_LOCK = threading.Lock()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    fence = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', text, re.S)
    return json.loads(fence[1] if fence else text, object_pairs_hook=pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + v)))


def compare(expected, actual, path='$'):
    """Object subset allows provenance; arrays/order/types must remain exact."""
    if type(expected) is not type(actual):
        return [path + ': type mismatch']
    if isinstance(expected, dict):
        return [error for key, value in expected.items() for error in
                ([path + '.' + key + ': missing'] if key not in actual else compare(value, actual[key], path + '.' + key))]
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path + ': array length mismatch']
        return [error for i, value in enumerate(expected) for error in compare(value, actual[i], f'{path}[{i}]')]
    return [] if expected == actual else [path + ': source fact mismatch']


def semantic_compare(case, actual):
    """Declaration order is not wire order; only explicitly source-backed unused types are optional."""
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items() if key != 'evidence'}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    expected, actual = clean(case['expected']), clean(actual)
    actual.pop('name', None)
    expected_type_names = {row['name'] for row in expected.get('types', [])}
    allowed = {row['name']: row for row in case.get('optional_source_types', [])}
    kept = []
    for row in actual.get('types', []):
        name = row.get('name')
        if name not in expected_type_names and name in allowed:
            errors = (compare(allowed[name], row, '$.optional_source_types.' + name)
                      + compare(row, allowed[name], '$.optional_source_types.' + name))
            if errors:
                return errors
        else:
            kept.append(row)
    actual['types'] = kept
    for value in (expected, actual):
        for key in ('types', 'enums'):
            value[key] = sorted(value.get(key, []), key=lambda row: row['name'])
        for enum in value['enums']:
            enum['items'] = sorted(enum['items'], key=lambda row: row['name'])
    # Extra semantic attributes are source claims too, even if the IR validator permits them.
    return compare(expected, actual) + compare(actual, expected)


def blocked(value, facts):
    if not isinstance(value, dict) or set(value) != {'status', 'unresolved'} or value['status'] != 'BLOCKED':
        return False
    if not isinstance(value['unresolved'], list) or not value['unresolved']:
        return False
    if not all(isinstance(item, str) and item.strip() for item in value['unresolved']):
        return False
    text = json.dumps(value['unresolved']).lower()
    if ('endian' in facts and re.search(r'\b(big|little)\b', text)
            and (re.search(r'\b(assum\w*|guess\w*|default\w*)\b', text)
                 or re.search(r'endian(?:ness)?\s*[:=]\s*(big|little)', text))):
        return False
    aliases = {'endian': r'endian|byte[\s-]+order', 'conflict': r'conflict|contradict|disagree|inconsisten',
               'header': r'header', 'variable': r'variabl|dynamic|count.depend',
               'layout': r'layout|padding|alignment|packing|\babi\b', 'authority': r'authorit|precedence'}
    return all(bool(re.search(aliases.get(fact, re.escape(fact.lower())), text)) for fact in facts)


def check_artifact(case, xml, unit, udpsim_root):
    """Core plus independent positive/negative payload checks, including multi-message inputs."""
    common = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    with CORE_LOCK:
        core = command(common + [SKILL / 'scripts/Test-IcdXml.ps1', '-UdpSimRoot', udpsim_root, '-IcdPath', xml], unit, 'core')
        passed = core['exit_code'] == 0 and 'XML_PASS' in core['stdout']
        checks = case.get('packet_checks', [case])
        for index, packet_case in enumerate(checks):
            target = unit if len(checks) == 1 else unit / f'packet-{index + 1}'
            target.mkdir(parents=True, exist_ok=True)
            payload, expected = target / 'payload.hex', target / 'expected.json'
            payload.write_text(packet_case['payload_hex'], encoding='ascii')
            save(expected, packet_case['expected_values'])
            packet_args = common + [SKILL / 'scripts/Test-UdpPayload.ps1', '-UdpSimRoot', udpsim_root, '-IcdPath', xml,
                                    '-PayloadPath', payload, '-Message', packet_case['packet_message'], '-ExpectedPath', expected]
            if 'expected_seq' in packet_case:
                packet_args += ['-ExpectedSeq', packet_case['expected_seq']]
            packet = command(packet_args + ['-ReportPath', target / 'packet.json'], target, 'packet-check')
            wrong = dict(packet_case['expected_values'])
            first = next(iter(wrong))
            wrong[first] = '1' if wrong[first] == '0' else '0'
            wrong_path = target / 'expected-wrong.json'
            save(wrong_path, wrong)
            negative_args = list(packet_args)
            negative_args[negative_args.index('-ExpectedPath') + 1] = wrong_path
            negative = command(negative_args + ['-ReportPath', target / 'packet-negative.json'], target, 'packet-negative-check')
            positive_report = json.loads((target / 'packet.json').read_text(encoding='utf-8-sig')) if (target / 'packet.json').exists() else {}
            negative_report = json.loads((target / 'packet-negative.json').read_text(encoding='utf-8-sig')) if (target / 'packet-negative.json').exists() else {}
            passed = passed and (packet['exit_code'] == 0 and positive_report.get('status') == 'PACKET_EXPECTED_MATCH'
                                 and negative['exit_code'] == 1
                                 and any('Value mismatch' in error for error in negative_report.get('errors', [])))
    return passed


def command(args, folder, label, timeout=180):
    try:
        result = subprocess.run([str(x) for x in args], cwd=ROOT, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
        data = {'command': [str(x) for x in args], 'exit_code': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr}
    except subprocess.TimeoutExpired:
        data = {'command': [str(x) for x in args], 'exit_code': -1, 'stderr': 'PROCESS_TIMEOUT', 'stdout': ''}
    save(folder / (label + '.json'), data)
    return data


def source_text(case):
    path = FIXTURES / case['input']
    if path.suffix.lower() != '.pdf':
        return path.read_text(encoding='utf-8-sig')
    from pypdf import PdfReader
    return '\n\n'.join(f'[PHYSICAL PDF PAGE {i + 1}]\n' + page.extract_text()
                        for i, page in enumerate(PdfReader(path).pages))


def fingerprint(udpsim):
    paths = sorted(p for base in (SKILL, FIXTURES) for p in base.rglob('*') if p.is_file() and '__pycache__' not in str(p))
    paths += [Path(__file__), ROOT / 'tools/udpsim_opencode_api.py']
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    for path in sorted(p for base in ('src', 'tools/xml', 'docs/wiki') for p in (udpsim / base).rglob('*')
                       if p.is_file() and not {'obj', 'bin'}.intersection(p.parts)
                       and p.suffix in ('.cs', '.csproj', '.ps1', '.md')):
        digest.update(path.relative_to(udpsim).as_posix().encode())
        digest.update(path.read_bytes())
    digest.update(subprocess.check_output(['git', '-C', str(udpsim), 'rev-parse', 'HEAD']))
    return digest.hexdigest()


def prompt_for(case, udpsim=None):
    refs = ['SKILL.md', 'references/workflow.md', 'references/intermediate-format.md', 'references/input-source.md', 'references/input-pdf.md']
    rules = '\n\n'.join(f'[{name}]\n' + (SKILL / name).read_text(encoding='utf-8') for name in refs)
    if udpsim:
        for name in ('xml-authoring-guide.md', 'file-formats.md'):
            rules += '\n\n[UdpSim docs/wiki/' + name + ']\n' + (udpsim / 'docs/wiki' / name).read_text(encoding='utf-8-sig')
    return (rules + '\n\nBROKERED EVALUATION TASK\n' + case['request'] +
            '\nThe host executes validation/conversion/Core tools after your response. Do not call tools or inspect files. '
            'Use only the supplied source. Return exactly one complete intermediate JSON object, no commentary. '
            'When a mandatory source fact is missing/conflicting or a required wire feature is unsupported, return only {"status":"BLOCKED","unresolved":["name the actual missing/conflicting/unsupported fact"]}. '
            'Do not guess missing facts. Retain exact source names, ordering and declared structure.\n'
            + '[SOURCE ' + case['input'] + ']\n' + source_text(case))


def evaluate(model, case, repeat, args, stamp):
    folder = args.work_dir / model / case['id'] / str(repeat)
    final = folder / 'result.json'
    if args.resume and final.exists():
        cached = json.loads(final.read_text(encoding='utf-8'))
        if cached.get('fingerprint') == stamp:
            return cached
    folder.mkdir(parents=True, exist_ok=True)
    summary = {'qualification': 'OPENCODE_BROKERED_SKILL_QA', 'model': model, 'case': case['id'],
               'repeat': repeat, 'fingerprint': stamp, 'status': 'FAIL', 'attempts': [], 'target_model': 'NOT_RUN'}
    if args.replay_from:
        previous = args.replay_from / model / case['id'] / str(repeat) / 'result.json'
        summary['replayed_from'] = str(previous)
        summary['generation_fingerprint'] = json.loads(previous.read_text(encoding='utf-8'))['fingerprint']
    base = prompt_for(case, args.udpsim_root)
    if case.get('seed_input'):
        seed = FIXTURES / case['seed_input']
        diagnostic = command([sys.executable, SKILL / 'scripts/icd_tool.py', 'validate', '--input', seed], folder, 'seed-validation')
        if diagnostic['exit_code'] != 1 or 'length_mismatch' not in diagnostic['stdout']:
            raise ValueError('Invalid repair fixture diagnostic')
        base += '\n[INVALID SEED]\n' + seed.read_text(encoding='utf-8') + '\n[ACTUAL VALIDATOR]\n' + diagnostic['stdout']
    if args.replay_from:
        original_prompt = args.replay_from / model / case['id'] / str(repeat) / 'attempt-1/prompt.txt'
        if original_prompt.read_text(encoding='utf-8') != base:
            raise ValueError('Replay requires unchanged source/Skill/task prompt; run a new model measurement')
    prompt = base
    for attempt in range(1, args.max_attempts + 1):
        unit = folder / f'attempt-{attempt}'
        unit.mkdir(parents=True, exist_ok=True)
        prompt_path = unit / 'prompt.txt'
        prompt_path.write_text(prompt, encoding='utf-8')
        if args.replay_from:
            old_unit = args.replay_from / model / case['id'] / str(repeat) / f'attempt-{attempt}'
            if not (old_unit / 'model.json').exists():
                summary['attempts'].append({'attempt': attempt, 'status': 'NOT_RUN', 'error': 'NO_RECORDED_RESPONSE'})
                summary['status'] = 'NOT_RUN'
                break
            response = json.loads((old_unit / 'model.json').read_text(encoding='utf-8'))
            prompt_path.write_text((old_unit / 'prompt.txt').read_text(encoding='utf-8'), encoding='utf-8')
            save(unit / 'model.json', response)
        else:
            response = command([sys.executable, ROOT / 'tools/udpsim_opencode_api.py', 'ask', '--model', model,
                                '--prompt-file', prompt_path, '--timeout', args.timeout], unit, 'model', args.timeout + 25)
        entry = {'attempt': attempt, 'status': 'FAIL'}
        summary['attempts'].append(entry)
        try:
            envelope = json.loads(response['stdout'])
            entry.update({k: envelope.get(k) for k in ('session_id', 'model_returned', 'cost_reported')})
            if response['exit_code'] or envelope.get('status') != 'OPENCODE_RESPONSE':
                entry['status'] = 'INFRA_FAILURE'
                entry['error'] = envelope.get('status', response['stderr'])
                break
            text = envelope['text']
            value = strict_json(text)
            if case['kind'] == 'ambiguous':
                if blocked(value, case['missing_facts']):
                    entry['status'] = 'PASS'
                elif isinstance(value, dict) and value.get('status') == 'BLOCKED':
                    entry['status'] = 'BLOCK_CONTRACT_FAIL'
                else:
                    entry['status'] = 'UNSAFE_COMPLETION'
                summary['status'] = entry['status']
                break
            candidate = unit / 'candidate.json'
            save(candidate, value)
            check = command([sys.executable, SKILL / 'scripts/icd_tool.py', 'validate', '--input', candidate], unit, 'ir')
            if check['exit_code']:
                entry['error'] = 'IR_FAIL'
                prompt = base + '\n[PREVIOUS CANDIDATE]\n' + text + '\n[ACTUAL VALIDATOR FEEDBACK]\n' + check['stdout']
                continue
            differences = semantic_compare(case, value)
            if differences:
                entry['error'] = 'SOURCE_MISMATCH'
                save(unit / 'oracle-comparison.json', differences)
                break
            xml = unit / 'message.icd.xml'
            converted = command([sys.executable, SKILL / 'scripts/icd_tool.py', 'convert', '--input', candidate, '--output', xml], unit, 'convert')
            if converted['exit_code']:
                entry['error'] = 'CONVERT_FAIL'
                break
            if check_artifact(case, xml, unit, args.udpsim_root):
                entry['status'] = summary['status'] = 'PASS'
            else:
                entry['error'] = 'CORE_OR_PACKET_FAIL'
            break
        except (ValueError, KeyError, TypeError) as error:
            entry['error'] = 'RESPONSE_FORMAT: ' + str(error)
            prompt = base + '\n[FORMAT FEEDBACK]\nReturn one strict JSON object only. ' + str(error)
    if summary['attempts'][-1]['status'] == 'INFRA_FAILURE':
        summary['status'] = 'INFRA_FAILURE'
    save(final, summary)
    print(f'{model} {case["id"]} repeat={repeat} {summary["status"]}', flush=True)
    return summary


def main():
    global FIXTURES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=(*MODELS, 'all'), default='all')
    parser.add_argument('--case')
    parser.add_argument('--suite', choices=('baseline', 'priority'), default='baseline')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--max-attempts', type=int, choices=range(1, 4), default=3)
    parser.add_argument('--timeout', type=int, choices=range(1, 181), default=180)
    parser.add_argument('--udpsim-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, default=ROOT / 'out/udpsim-opencode-eval')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--replay-from', type=Path, help='Rejudge recorded responses without new model calls; preserve original evidence')
    args = parser.parse_args()
    if args.suite == 'priority':
        FIXTURES = ROOT / 'tests/fixtures/udpsim-priority-qa'
    args.work_dir = args.work_dir.resolve()
    if args.replay_from:
        args.replay_from = args.replay_from.resolve()
        if not args.replay_from.is_relative_to((ROOT / 'out').resolve()) or args.replay_from == args.work_dir:
            parser.error('Replay source must be a distinct directory under ignored out/')
    if not args.work_dir.is_relative_to((ROOT / 'out').resolve()) or not 1 <= args.repeat <= 10:
        parser.error('Use work-dir under ignored out/ and repeat 1..10')
    cases = json.loads((FIXTURES / 'cases.json').read_text(encoding='utf-8-sig'))['cases']
    if args.case:
        cases = [case for case in cases if case['id'] == args.case]
        if not cases:
            parser.error('Unknown case')
    stamp = fingerprint(args.udpsim_root)
    jobs = [(model, case, i) for case in cases for i in range(1, args.repeat + 1)
            for model in (MODELS if args.model == 'all' else (args.model,))]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda job: evaluate(*job, args, stamp), jobs))
    save(args.work_dir / 'summary.json', {'fingerprint': stamp, 'results': results})
    return 0 if all(row['status'] == 'PASS' for row in results) else 1


if __name__ == '__main__':
    sys.exit(main())
