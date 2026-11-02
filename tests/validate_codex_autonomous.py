"""Judge completed Codex tool-driven actors. Does not generate answers or call a model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import udpsim_native_qa as N


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--udpsim-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    if not root.is_relative_to((ROOT / 'out').resolve()):
        parser.error('Use ignored actor workspaces under out/')
    cases = json.loads((N.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases']
    rows = []
    for case in cases:
        work = root / case['id']
        try:
            result = N.judge(work, case, args.udpsim_root, interrupted=case['id'] == 'resume-repair')
            events = N.audit(work)
            state = N.Adapter(work).fresh(('XML_PASS', 'BLOCKED'))
            result.update(case=case['id'], qualification='CODEX_TOOL_DRIVEN_AGENT_QA',
                          tool_calls=len(events), checkpoint_inputs_hash=state['inputs_hash'],
                          stage=state['stage'], packet_check_executor='parent' if case['kind'] != 'ambiguous' else 'NOT_RUN',
                          internal_target='NOT_RUN')
        except (ValueError, OSError, KeyError, TypeError) as error:
            result = {'case': case['id'], 'status': 'FAIL', 'error': str(error), 'internal_target': 'NOT_RUN'}
        N.E.save(work / 'parent-verdict.json', result)
        rows.append(result)
        print(case['id'] + ' ' + result['status'], flush=True)
    value = {'status': 'CODEX_TOOL_AGENT_PASS' if all(row['status'] == 'PASS' for row in rows) else 'FAIL',
             'executor': 'fresh Codex agents using restricted CLI -> actual stdio MCP tools',
             'model_identity': 'inherited Codex session model; internal Qwen equivalence not established',
             'model_answer_source': 'actors interpreted raw synthetic input; evaluator oracles not copied/provided',
             'packet_check_executor': 'parent', 'internal_target': 'NOT_RUN', 'results': rows,
             'evaluator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    N.E.save(root / 'summary.json', value)
    return 0 if value['status'] == 'CODEX_TOOL_AGENT_PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
