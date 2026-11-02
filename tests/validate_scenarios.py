"""Actual Core scenario generation checks. All source/intent values are synthetic; no sockets/model calls."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import run_udpsim_opencode_eval as E


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udpsim-root', type=Path, required=True)
    args = parser.parse_args()
    work = ROOT / 'out/scenario-qa' / uuid.uuid4().hex[:12]
    work.mkdir(parents=True)
    inputs = work / 'inputs'
    shutil.copytree(ROOT / 'tests/fixtures/scenarios', inputs)
    context, config = work / 'context.json', inputs / 'UdpSim.config.xml'
    scripts = ROOT / 'skills/udpsim-icd-authoring/scripts'
    common = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
    results = []

    def run(label, command, expected=0, marker=None):
        result = E.command(command, work, label)
        assert result['exit_code'] == expected, (label, result)
        if marker:
            assert marker in result['stdout'], (label, result)
        results.append({'name': label, 'status': 'PASS', 'observed_exit': result['exit_code']})
        return result

    export = common + [scripts / 'Export-ScenarioContext.ps1', '-UdpSimRoot', args.udpsim_root, '-ConfigPath', config, '-OutputPath', context]
    run('export-real-Core', export, marker='CONTEXT_EXPORTED')
    scoped = list(export)
    scoped[scoped.index('-OutputPath') + 1] = work / 'scoped-context.JSON'
    run('export-exact-ICD-key', scoped + ['-IcdKey', 'device.icd.xml'], marker='CONTEXT_EXPORTED')
    assert len(json.loads((work / 'scoped-context.JSON').read_text(encoding='utf-8'))['icds']) == 1
    snapshot = json.loads(context.read_text(encoding='utf-8'))
    device = next(item for item in snapshot['icds'] if item['key'] == 'device.icd.xml')
    assert device['targets'] == ['DEMO-A', 'DEMO-B']
    assert len(device['send'][0]['body']) == 6
    assert device['send'][0]['automatic_header'] == ['Id', 'Length', 'Sequence']
    assert [f['path'] for f in device['send'][0]['user_header']] == ['Source']
    python = [sys.executable, scripts / 'scenario_tool.py']
    run('catalog', python + ['catalog', '--context', context], marker='SCENARIO_CATALOG')
    run('fields', python + ['fields', '--context', context, '--icd', 'device.icd.xml', '--message', 'SET_CHANNELS'], marker='Channels[1].Flags.Mode')
    intent = json.loads((inputs / 'intent.json').read_text(encoding='utf-8'))
    plans = []
    for kind in ('Periodic', 'Manual', 'Response'):
        path = work / (kind + '.json')
        command = python + ['template', '--context', context, '--kind', kind, '--icd', 'device.icd.xml', '--message', 'SET_CHANNELS', '--output', path]
        if kind == 'Response':
            command += ['--trigger', 'REPORT_CHANNELS']
        run('template-' + kind, command, marker='SCENARIO_TEMPLATE_CREATED')
        plan = json.loads(path.read_text(encoding='utf-8'))
        entry = plan['entries'][0]
        assert entry['values'] == {field['path']: None for field in device['send'][0]['body']}
        entry['targets'] = '*' if kind == 'Response' else ['DEMO-A']
        if kind == 'Periodic':
            entry['period_ms'] = intent['period_ms']
        E.save(path, plan)
        run('null-values-' + kind, python + ['generate', '--context', context, '--plan', path, '--output', work / (kind + '.xml')], 1, 'unresolved_values')
        assert not (work / (kind + '.xml')).exists()
        entry['values'] = copy.deepcopy(intent['values'])
        if kind == 'Manual':
            entry['values']['Source'] = intent['manual_source']
        if kind == 'Response':
            entry.update(delay_ms=intent['delay_ms'], conditions=intent['condition'])
        plans.append(plan)
    combined = copy.deepcopy(plans[0])
    combined['name'] = intent['name']
    combined['entries'] = [plans[2]['entries'][0], plans[1]['entries'][0], plans[0]['entries'][0]]
    plan_path, xml = work / 'complete.json', work / 'complete.scenario.xml'
    E.save(plan_path, combined)
    run('generate-combined', python + ['generate', '--context', context, '--plan', plan_path, '--output', xml], marker='SCENARIO_DRAFT_CREATED')
    data = xml.read_bytes()
    assert data.startswith(b'\xef\xbb\xbf') and b'\n' not in data.replace(b'\r\n', b'')
    tree = ET.fromstring(data)
    assert [node.tag for node in tree] == ['Periodic', 'Manual', 'Response']
    assert len(tree.findall('.//Value')) == 19
    assert tree[-1].find('Condition').attrib == {'field': 'Channels[1].Flags.Ready', 'value': 'On'}
    gate = common + [scripts / 'Test-ScenarioXml.ps1', '-UdpSimRoot', args.udpsim_root, '-ConfigPath', config]
    run('actual-Core-three-kinds', gate + ['-ScenarioPath', xml], marker='SCENARIO_PASS')
    mutations = [
        ('disabled-target', lambda p: p['entries'][0].update(targets=['DEMO-C']), 'targets'),
        ('wrong-icd-target', lambda p: p['entries'][0].update(targets=['DEMO-D']), 'targets'),
        ('automatic-header', lambda p: p['entries'][0]['values'].update(Sequence='1'), 'automatic_header_forbidden'),
        ('header-condition', lambda p: p['entries'][0].update(conditions={'Source': '7'}), 'condition_field'),
        ('wrong-trigger', lambda p: p['entries'][0].update(trigger='SET_CHANNELS'), 'message_direction'),
        ('wrong-path', lambda p: p['entries'][0]['values'].update({'Channels[9].Reading': '1'}), 'unknown_field'),
        ('wide-bits', lambda p: p['entries'][0]['values'].update({'Channels[0].Flags.Mode': '8'}), 'value_range'),
        ('stale-plan', lambda p: p.update(context_sha256='0'*64), 'STALE_PLAN'),
    ]
    for label, mutate, marker in mutations:
        bad = copy.deepcopy(combined)
        mutate(bad)
        bad_path = work / (label + '.json')
        E.save(bad_path, bad)
        run(label, python + ['generate', '--context', context, '--plan', bad_path, '--output', xml], 1, marker)
        assert xml.read_bytes() == data
    invalid = ET.fromstring(data)
    invalid[0].remove(invalid[0].find('Value'))
    bad_xml = work / 'missing-value.scenario.xml'
    bad_xml.write_bytes(ET.tostring(invalid, encoding='utf-8'))
    run('Core-rejects-missing-value', gate + ['-ScenarioPath', bad_xml], 1, 'SCENARIO_FAIL')
    run('missing-toolchain', gate + ['-ScenarioPath', xml, '-MSBuildPath', work / 'missing-MSBuild.exe'], 2, 'BLOCKED_ENV')
    source = inputs / 'icds/device.icd.xml'
    source.write_bytes(source.read_bytes() + b'\n')
    run('stale-context', python + ['generate', '--context', context, '--plan', plan_path, '--output', xml], 1, 'STALE_CONTEXT')
    assert xml.read_bytes() == data
    typo_config = inputs / 'bad-config.xml'
    original = config.read_text(encoding='utf-8')
    typo_config.write_text(original.replace('enabled="true"', 'enable="true"'), encoding='utf-8')
    typo = run('strict-Config-typo', common + [scripts / 'Test-ScenarioXml.ps1', '-UdpSimRoot', args.udpsim_root, '-ConfigPath', typo_config, '-ScenarioPath', xml], 1, 'SCENARIO_FAIL')
    assert 'enable' in (typo['stdout'] + typo['stderr'])
    result = {'status': 'SCENARIO_TOOLS_PASS', 'checks': len(results), 'results': results, 'model_qa': 'NOT_RUN', 'internal_target': 'NOT_RUN'}
    E.save(work / 'summary.json', result)
    print(json.dumps({'work': str(work), **result}, ensure_ascii=False))


if __name__ == '__main__':
    main()
