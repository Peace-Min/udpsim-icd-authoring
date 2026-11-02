"""Actual stdio MCP/Core/packet fixture checks. Scripted client, never a model-quality pass."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import udpsim_native_qa as N


class Client:
    def __init__(self, work):
        self.child = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'tools/udpsim_agent_mcp.py'), '--workspace', str(work)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        self.index = 0
        self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'scripted-fixture', 'version': '1'}})
        self.child.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        self.child.stdin.flush()
        assert len(self.request('tools/list', {})['tools']) == 7

    def request(self, method, params):
        self.index += 1
        self.child.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': self.index, 'method': method, 'params': params}) + '\n')
        self.child.stdin.flush()
        reply = json.loads(self.child.stdout.readline())
        assert reply.get('id') == self.index and 'result' in reply, reply
        return reply['result']

    def call(self, tool, args=None, failure=False):
        result = self.request('tools/call', {'name': tool, 'arguments': args or {}})
        assert result['isError'] is failure, result
        return json.loads(result['content'][0]['text'])

    def close(self):
        if not self.child.stdin.closed:
            self.child.stdin.close()
        self.child.wait(timeout=15)
        assert self.child.returncode == 0, self.child.stderr.read()
        self.child.stdout.close(); self.child.stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udpsim-root', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((N.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases']
    out = ROOT / 'out/udpsim-priority-qa' / ('tools-' + uuid.uuid4().hex[:10])
    results = []
    for case in cases:
        interrupted = case['id'] == 'resume-repair'
        work = N.prepare(out / case['id'], case, args.udpsim_root, interrupted)
        (work / 'control/phase.txt').write_text('before-interrupt' if interrupted else 'single', encoding='utf-8')
        client = Client(work)
        try:
            client.call('read', {'resource': 'skill'})
            if case['input'].endswith('.pdf'):
                client.call('source', {'first_page': 2, 'last_page': 4})
                client.call('source', {'first_page': 1, 'last_page': 1})
            else:
                client.call('source')
            if case['kind'] == 'ambiguous':
                client.call('block', {'unresolved': [fact + ' is unavailable, conflicting or unsupported' for fact in case['missing_facts']]})
            else:
                if case.get('seed_input'):
                    bad = client.call('validate', failure=True)
                    assert bad['status'] == 'IR_FAIL' and 'length_mismatch' in bad['stdout']
                oracle = (N.FIXTURES / (case['id'] + '.expected.json')).read_text(encoding='utf-8')
                client.call('save', {'definition_json': oracle})
                assert client.call('validate')['status'] == 'IR_PASS'
                if interrupted:
                    client.call('convert', failure=True)
                    client.close()
                    (work / 'control/pause.flag').unlink()
                    (work / 'control/resumed.flag').write_text('actual MCP process restart', encoding='utf-8')
                    (work / 'control/phase.txt').write_text('after-resume', encoding='utf-8')
                    client = Client(work)
                    assert client.call('read', {'resource': 'checkpoint'})['stage'] == 'IR_PASS'
                assert client.call('convert')['status'] == 'XML_WRITTEN'
                assert client.call('validate_xml')['status'] == 'XML_PASS'
            result = N.judge(work, case, args.udpsim_root, interrupted)
            assert result['status'] == 'PASS', result
            results.append({'case': case['id'], 'status': 'TOOLS_PASS', 'executor': 'scripted_mcp_client', 'model_qa': 'NOT_RUN'})
            print(case['id'] + ' TOOLS_PASS', flush=True)
        finally:
            client.close()
    assert len(list(out.rglob('packet.json'))) == 4
    assert len(list(out.rglob('packet-negative.json'))) == 4
    N.E.save(out / 'summary.json', {'status': 'PRIORITY_TOOLS_PASS', 'model_qa': 'NOT_RUN', 'results': results})
    print('PRIORITY_TOOLS_PASS ' + str(out), flush=True)


if __name__ == '__main__':
    main()
