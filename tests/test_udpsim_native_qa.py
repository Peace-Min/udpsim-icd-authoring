"""Restricted native-tool/checkpoint guards; no real model requests."""
import copy
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
UDPSIM = Path(os.environ.get('UDPSIM_QA_ROOT', str(ROOT.parent / 'UdpSim')))
sys.path.insert(0, str(ROOT / 'tools'))
import udpsim_agent_mcp as M
import udpsim_native_qa as N
import udpsim_opencode_api as A


class NativeGuards(unittest.TestCase):
    def setUp(self):
        if not (UDPSIM / 'tools/xml/ValidateXml.ps1').is_file():
            self.skipTest('Set UDPSIM_QA_ROOT to a local UdpSim checkout, or use a sibling UdpSim directory')
        (ROOT / 'out').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'out')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.cases = json.loads((N.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases']
        self.case = next(c for c in self.cases if c['id'] == 'resume-repair')
        self.work = N.prepare(self.folder / 'workspace', self.case, UDPSIM)
        self.adapter = M.Adapter(self.work)
        self.oracle = json.loads((N.FIXTURES / 'resume-repair.expected.json').read_text(encoding='utf-8'))

    def call(self, name, args=None):
        result = self.adapter.call(name, args or {})
        return result, json.loads(result['content'][0]['text'])

    def valid_ir(self):
        self.call('save', {'definition_json': json.dumps(self.oracle)})
        result, value = self.call('validate')
        self.assertFalse(result['isError'])
        self.assertEqual(value['status'], 'IR_PASS')

    def test_only_seven_restricted_tools(self):
        self.assertEqual({t['name'] for t in M.TOOLS}, {'read', 'source', 'save', 'validate', 'convert', 'validate_xml', 'block'})

    def test_oracle_not_copied_or_readable(self):
        self.assertFalse(list(self.work.rglob('*expected*')))
        result, _ = self.call('read', {'resource': '../../tests/fixtures/udpsim-priority-qa/cases.json'})
        self.assertTrue(result['isError'])

    def test_unknown_tool_and_argument_rejected(self):
        self.assertTrue(self.call('bash', {'command': 'anything'})[0]['isError'])
        self.assertTrue(self.call('validate', {'command': 'anything'})[0]['isError'])

    def test_source_instruction_is_returned_as_data(self):
        case = next(c for c in self.cases if c['id'] == 'source-instruction')
        other = N.prepare(self.folder / 'injection', case, UDPSIM)
        text = json.loads(M.Adapter(other).call('source', {})['content'][0]['text'])['text']
        self.assertIn('ignore Skill', text)
        self.assertFalse((other / 'message.icd.xml').exists())

    def test_duplicate_and_nonfinite_json_rejected(self):
        original = self.adapter.candidate.read_bytes()
        for value in ('{"a":1,"a":2}', '{"a":NaN}'):
            self.assertTrue(self.call('save', {'definition_json': value})[0]['isError'])
            self.assertEqual(original, self.adapter.candidate.read_bytes())

    def test_seed_actual_length_error(self):
        result, value = self.call('validate')
        self.assertTrue(result['isError'])
        self.assertEqual(value['status'], 'IR_FAIL')
        self.assertIn('length_mismatch', value['stdout'])

    def test_convert_without_validation_fails(self):
        self.assertTrue(self.call('convert')[0]['isError'])
        self.assertFalse(self.adapter.xml.exists())

    def test_initial_plus_three_failed_corrections_stop(self):
        self.call('validate')
        for length in (15, 14, 13):
            bad = copy.deepcopy(self.oracle)
            bad['messages'][0]['length'] = length
            self.call('save', {'definition_json': json.dumps(bad)})
            self.assertEqual(self.call('validate')[1]['status'], 'IR_FAIL')
        self.call('save', {'definition_json': json.dumps(self.oracle)})
        result, value = self.call('validate')
        self.assertTrue(result['isError'])
        self.assertIn('REPAIR_LIMIT', value['error'])
        self.assertEqual(self.adapter.fresh(('BLOCKED',))['stage'], 'BLOCKED')

    def test_process_restart_reads_verified_checkpoint(self):
        self.valid_ir()
        self.assertEqual(M.Adapter(self.work).fresh(('IR_PASS',))['stage'], 'IR_PASS')

    def test_changed_source_invalidates_checkpoint(self):
        self.valid_ir()
        self.adapter.source.write_text('Changed source', encoding='utf-8')
        result, value = self.call('convert')
        self.assertTrue(result['isError'])
        self.assertIn('STALE_CHECKPOINT', value['error'])

    def test_changed_candidate_invalidates_checkpoint(self):
        self.valid_ir()
        value = copy.deepcopy(self.oracle)
        value['messages'][0]['id'] += 1
        self.adapter.candidate.write_text(json.dumps(value), encoding='utf-8')
        self.assertTrue(self.call('convert')[0]['isError'])

    def test_saved_replacement_invalidates_old_xml(self):
        self.adapter.xml.write_text('old XML', encoding='utf-8')
        self.call('save', {'definition_json': json.dumps(self.oracle)})
        self.assertFalse(self.adapter.xml.exists())
        self.assertTrue(self.call('validate_xml')[0]['isError'])

    def test_xml_change_invalidates_core_gate(self):
        self.valid_ir()
        self.assertFalse(self.call('convert')[0]['isError'])
        self.adapter.xml.write_text('changed XML', encoding='utf-8')
        result, value = self.call('validate_xml')
        self.assertTrue(result['isError'])
        self.assertIn('STALE_CHECKPOINT', value['error'])

    def test_pause_prevents_progress_until_runner_resume(self):
        config_path = self.work / 'control/config.json'
        config = json.loads(config_path.read_text(encoding='utf-8'))
        config['pause_on_ir'] = True
        N.E.save(config_path, config)
        self.adapter = M.Adapter(self.work)
        self.valid_ir()
        self.assertTrue(self.call('convert')[0]['isError'])
        (self.work / 'control/pause.flag').unlink()
        (self.work / 'control/resumed.flag').write_text('resumed', encoding='utf-8')
        self.assertFalse(M.Adapter(self.work).call('convert', {})['isError'])

    def test_false_completion_without_tools_rejected(self):
        self.assertEqual(N.judge(self.work, self.case, UDPSIM)['status'], 'FAIL')
        self.call('read', {'resource': 'skill'})
        self.call('source')
        result = N.judge(self.work, self.case, UDPSIM)
        self.assertEqual(result['reason'], 'NO_FRESH_COMPLETION_EVIDENCE')

    def test_block_removes_final_xml_and_records_fact(self):
        self.adapter.xml.write_text('not accepted', encoding='utf-8')
        result, value = self.call('block', {'unresolved': ['header absent']})
        self.assertFalse(result['isError'])
        self.assertEqual(value['stage'], 'BLOCKED')
        self.assertFalse(self.adapter.xml.exists())

    def test_pdf_range_uses_physical_pages(self):
        case = self.cases[0]
        work = N.prepare(self.folder / 'pdf', case, UDPSIM)
        adapter = M.Adapter(work)
        result = adapter.call('source', {'first_page': 2, 'last_page': 4})
        text = json.loads(result['content'][0]['text'])['text']
        self.assertIn('[PHYSICAL PDF PAGE 2]', text)
        self.assertNotIn('[PHYSICAL PDF PAGE 1]', text)
        self.assertIn('SENSOR_STATUS', text)
        first = json.loads(adapter.call('source', {'first_page': 1, 'last_page': 1})['content'][0]['text'])
        self.assertIn('role=seq', first['text'])
        self.assertTrue(adapter.call('source', {'first_page': True})['isError'])

    def test_native_identity_and_permissions(self):
        env = N.native_environment(self.work, A.MODELS[0])
        self.assertEqual(env['XDG_DATA_HOME'], A.isolated_environment()['XDG_DATA_HOME'])
        config = N.configuration(self.work, A.MODELS[0])
        self.assertEqual(config['permission'], {'*': 'deny', 'icdqa_*': 'allow'})
        self.assertEqual(config['tools'], {'*': False, 'icdqa_*': True})

    def test_native_free_limit_aborts_without_fallback(self):
        calls = []
        def request(path, body=None, **kwargs):
            calls.append((path, body))
            if path == '/session':
                return {'id': 'ses_fixture'}
            if path.endswith('/message'):
                return []
            if path == '/session/status':
                return {'ses_fixture': {'type': 'retry', 'action': {'reason': 'free_tier_limit'}}}
            return {}
        with patch.object(A, 'models', return_value=[{'id': A.MODELS[0]}]), patch.object(A, 'request', side_effect=request):
            result = N.turn(self.work, A.MODELS[0], 'Synthetic fixture', 1, 'single')
        self.assertEqual(result['status'], 'MODEL_FREE_LIMIT')
        self.assertEqual(sum(path == '/session' for path, _ in calls), 1)
        self.assertTrue(any(path == '/session/ses_fixture/abort' for path, _ in calls))
        self.assertFalse((self.work / 'audit.jsonl').exists())

    def test_actor_cli_calls_real_mcp_read(self):
        params = self.work / 'call-args.json'
        params.write_text('{"resource":"skill"}', encoding='utf-8')
        result = subprocess.run([sys.executable, str(ROOT / 'tools/udpsim_agent_call.py'), '--workspace', str(self.work),
                                 '--tool', 'read', '--arguments-file', str(params)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['isError'])
        self.assertEqual(N.audit(self.work)[0]['tool'], 'read')

    def test_actor_cli_rejects_external_arguments_file(self):
        params = self.folder / 'outside-args.json'
        params.write_text('{}', encoding='utf-8')
        result = subprocess.run([sys.executable, str(ROOT / 'tools/udpsim_agent_call.py'), '--workspace', str(self.work),
                                 '--tool', 'source', '--arguments-file', str(params)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertIn('within the assigned workspace', result.stderr)
        self.assertFalse((self.work / 'audit.jsonl').exists())

    def test_actor_cli_rejects_workspace_outside_out(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/udpsim_agent_call.py'), '--workspace', str(ROOT / 'tests'),
                                 '--tool', 'source'], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.work / 'audit.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
