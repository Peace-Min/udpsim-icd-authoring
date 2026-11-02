"""Local OpenCode client tests; no paid/free model calls or live service mutations."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('udpsim_opencode_api', ROOT / 'tools/udpsim_opencode_api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def assistant(text='QA_API_OK', *, completed=10, finish='stop', model=None, error=None):
    info = {'role': 'assistant', 'providerID': 'opencode', 'modelID': model or api.MODELS[0],
            'time': {'created': 1}, 'finish': finish, 'tokens': {'input': 7, 'output': 3}, 'cost': 0}
    if completed:
        info['time']['completed'] = completed
    if error:
        info['error'] = error
    return {'info': info, 'parts': [{'type': 'text', 'text': text}] if text is not None else [{'type': 'reasoning', 'text': 'still thinking'}]}


class OpenCodeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='udpsim-opencode-api-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.binary = self.folder / 'opencode.exe'
        self.binary.write_bytes(b'synthetic binary')
        for name, value in [('WORK', self.folder), ('SANDBOX', self.folder / 'workspace'), ('BINARY', self.binary)]:
            p = patch.object(api, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_config_whitelists_only_selected_free_models(self):
        config = api.configuration()
        self.assertEqual(config['enabled_providers'], ['opencode'])
        self.assertEqual(set(config['provider']['opencode']['whitelist']), set(api.MODELS))
        self.assertTrue(all(name.endswith('-free') for name in api.MODELS))
        self.assertEqual(config['small_model'], config['model'])

    def test_config_denies_shell_and_edit_by_default(self):
        config = api.configuration()
        self.assertEqual(config['permission']['*'], 'deny')
        self.assertEqual(config['permission']['read'], 'allow')
        self.assertEqual(config['share'], 'disabled')
        self.assertFalse(config['autoupdate'])
        self.assertLessEqual(config['agent']['qa']['steps'], 4)

    def test_isolated_environment_drops_credentials_without_changing_parent(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-secret', 'ANTHROPIC_AUTH_TOKEN': 'synthetic-token', 'OPENCODE_API_KEY': 'synthetic-opencode'}, clear=False):
            env = api.isolated_environment()
            self.assertNotIn('OPENAI_API_KEY', env)
            self.assertNotIn('ANTHROPIC_AUTH_TOKEN', env)
            self.assertNotIn('OPENCODE_API_KEY', env)
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'synthetic-secret')
        for kind in ('CONFIG', 'DATA', 'CACHE', 'STATE'):
            self.assertTrue(Path(env['XDG_' + kind + '_HOME']).is_relative_to(self.folder))

    def test_setup_rejects_wrong_native_version(self):
        with patch.object(api.sys, 'platform', 'win32'), patch.object(api.subprocess, 'check_output', return_value='9.9.9\n'):
            with self.assertRaisesRegex(ValueError, 'version'):
                api.setup()

    def test_start_does_not_replace_existing_service(self):
        with patch.object(api, 'health', return_value={'healthy': True}), patch.object(api.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'already'):
                api.start()
            spawn.assert_not_called()

    def test_start_runs_in_isolated_workspace(self):
        child = Mock(pid=190005)
        with patch.object(api, 'health', side_effect=[None, {'healthy': True}]), patch.object(api, 'prepare_workspace') as prepare, patch.object(api.socket, 'socket'), patch.object(api.subprocess, 'Popen', return_value=child) as spawn:
            api.start()
        prepare.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs['cwd'], self.folder / 'workspace')
        state = json.loads((self.folder / 'process.json').read_text())
        self.assertEqual(Path(state['workspace']), self.folder / 'workspace')

    def fixture_source_root(self):
        root = self.folder / 'source-bank'
        fixtures = root / 'tests/fixtures/udpsim-model'
        fixtures.mkdir(parents=True)
        for name in ('ping.h', 'ambiguous.h', 'document-excerpt.txt'):
            (fixtures / name).write_text('Synthetic raw input: ' + name, encoding='utf-8')
        (fixtures / 'expected.json').write_text('{"evaluator_only":"synthetic heldout oracle"}', encoding='utf-8')
        skill = root / 'skills/udpsim-icd-authoring'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('Synthetic runtime skill', encoding='utf-8')
        (skill / '__pycache__').mkdir()
        (skill / '__pycache__/ignored.pyc').write_bytes(b'synthetic cache')
        entry = root / '.claude/skills/udpsim-icd-authoring'
        entry.mkdir(parents=True)
        (entry / 'SKILL.md').write_text('Synthetic project entry', encoding='utf-8')
        return root

    def test_workspace_copies_raw_inputs_but_not_evaluator_or_cache(self):
        root = self.fixture_source_root()
        with patch.object(api, 'ROOT', root):
            api.prepare_workspace()
        sandbox = self.folder / 'workspace'
        self.assertEqual({p.name for p in (sandbox / 'fixtures').iterdir()}, {'ping.h', 'ambiguous.h', 'document-excerpt.txt'})
        self.assertFalse(list(sandbox.rglob('expected.json')))
        self.assertFalse(list(sandbox.rglob('*.pyc')))
        self.assertTrue((sandbox / 'skills/udpsim-icd-authoring/SKILL.md').is_file())
        self.assertTrue((sandbox / '.claude/skills/udpsim-icd-authoring/SKILL.md').is_file())

    def test_workspace_is_its_own_git_discovery_boundary(self):
        root = self.fixture_source_root()
        with patch.object(api, 'ROOT', root):
            api.prepare_workspace()
        sandbox = self.folder / 'workspace'
        actual = api.subprocess.check_output(['git', '-C', str(sandbox), 'rev-parse', '--show-toplevel'], text=True).strip()
        self.assertEqual(Path(actual).resolve(), sandbox.resolve())

    def test_stop_refuses_recycled_pid(self):
        api.save(self.folder / 'process.json', {'pid': 190004, 'executable': str(self.binary)})
        process = {'ExecutablePath': str(self.folder / 'someone-else.exe'), 'CommandLine': '--port 18090'}
        with patch.object(api.subprocess, 'check_output', return_value=json.dumps(process)), patch.object(api.subprocess, 'run') as kill:
            with self.assertRaisesRegex(ValueError, 'identity'):
                api.stop()
            kill.assert_not_called()

    def test_stop_refuses_same_binary_other_port(self):
        api.save(self.folder / 'process.json', {'pid': 190004, 'executable': str(self.binary)})
        process = {'ExecutablePath': str(self.binary), 'CommandLine': 'opencode.exe serve --port 18091'}
        with patch.object(api.subprocess, 'check_output', return_value=json.dumps(process)), patch.object(api.subprocess, 'run') as kill:
            with self.assertRaisesRegex(ValueError, 'identity'):
                api.stop()
            kill.assert_not_called()

    def test_models_rejects_changed_price(self):
        data = {'providers': [{'id': 'opencode', 'models': {api.MODELS[0]: {'cost': {'input': 0, 'output': 1}}}}]}
        with patch.object(api, 'request', return_value=data):
            with self.assertRaisesRegex(ValueError, 'free'):
                api.models()

    def test_models_only_exposes_allowed_free_names(self):
        data = {'providers': [{'id': 'opencode', 'models': {api.MODELS[0]: {'cost': {'input': 0, 'output': 0}}, 'paid-model': {'cost': {'input': 1, 'output': 1}}}}]}
        with patch.object(api, 'request', return_value=data):
            self.assertEqual([row['id'] for row in api.models()], [api.MODELS[0]])

    def test_user_message_is_not_assistant_response(self):
        self.assertIsNone(api.result_of([{'info': {'role': 'user'}, 'parts': [{'type': 'text', 'text': 'QA_API_OK'}]}], 'ses_synthetic', api.MODELS[0]))

    def test_unfinished_assistant_is_not_a_response(self):
        self.assertIsNone(api.result_of([assistant(completed=None)], 'ses_synthetic', api.MODELS[0]))

    def test_reasoning_only_is_not_a_response(self):
        result = api.result_of([assistant(text=None)], 'ses_synthetic', api.MODELS[0])
        self.assertTrue(result is None or result.get('status') != 'OPENCODE_RESPONSE')

    def test_old_completed_text_cannot_beat_new_pending_assistant(self):
        messages = [assistant(text='old text'), assistant(text='new pending', completed=None)]
        self.assertIsNone(api.result_of(messages, 'ses_synthetic', api.MODELS[0]))

    def test_tool_call_turn_does_not_complete_the_run(self):
        message = assistant(text='I will read the source now', finish='tool-calls')
        result = api.result_of([message], 'ses_synthetic', api.MODELS[0])
        self.assertTrue(result is None or result.get('status') != 'OPENCODE_RESPONSE')

    def test_length_limited_output_is_not_success(self):
        result = api.result_of([assistant(finish='length')], 'ses_synthetic', api.MODELS[0])
        self.assertTrue(result is not None and result.get('status') != 'OPENCODE_RESPONSE')

    def test_wrong_returned_model_is_not_success(self):
        result = api.result_of([assistant(model='different-model')], 'ses_synthetic', api.MODELS[0])
        self.assertTrue(result is not None and result.get('status') != 'OPENCODE_RESPONSE')

    def test_wrong_returned_provider_is_not_success(self):
        message = assistant()
        message['info']['providerID'] = 'different-provider'
        result = api.result_of([message], 'ses_synthetic', api.MODELS[0])
        self.assertTrue(result is not None and result.get('status') != 'OPENCODE_RESPONSE')

    def test_error_envelope_not_success_even_if_it_has_text(self):
        result = api.result_of([assistant(error={'name': 'APIError', 'data': {'message': 'synthetic error'}})], 'ses_synthetic', api.MODELS[0])
        self.assertEqual(result['status'], 'MODEL_ERROR')

    def test_completed_assistant_yields_text_and_does_not_claim_skill_pass(self):
        result = api.result_of([assistant()], 'ses_synthetic', api.MODELS[0])
        self.assertEqual(result['status'], 'OPENCODE_RESPONSE')
        self.assertEqual(result['text'], 'QA_API_OK')
        self.assertEqual(result['skill_qa'], 'NOT_RUN')

    def test_response_records_native_assistant_steps(self):
        prior = assistant(text='Reading fixture', finish='tool-calls')
        result = api.result_of([prior, assistant()], 'ses_synthetic', api.MODELS[0])
        self.assertEqual(result['assistant_steps'], 2)

    def test_malformed_message_list_envelopes_fail_explicitly(self):
        for messages in ({'messages': []}, None, ['wrong item'], [{'info': None}]):
            with self.subTest(messages=messages), self.assertRaisesRegex(ValueError, 'message-list'):
                api.result_of(messages, 'ses_synthetic', api.MODELS[0])

    def test_malformed_assistant_time_or_parts_fail_explicitly(self):
        for field, value in [('time', None), ('parts', {}), ('parts', ['wrong item'])]:
            message = assistant()
            if field == 'time':
                message['info']['time'] = value
            else:
                message[field] = value
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, 'assistant envelope'):
                api.result_of([message], 'ses_synthetic', api.MODELS[0])

    def test_nonstring_final_text_is_not_success(self):
        for value in (None, 7, {}, []):
            message = assistant()
            message['parts'][0]['text'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'string'):
                api.result_of([message], 'ses_synthetic', api.MODELS[0])

    def test_empty_completed_text_is_explicit_failure(self):
        result = api.result_of([assistant(text='   ')], 'ses_synthetic', api.MODELS[0])
        self.assertEqual(result['status'], 'MODEL_EMPTY_RESPONSE')

    def test_paid_model_rejected_before_network(self):
        with patch.object(api, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'free'):
                api.ask('paid-model', 'synthetic prompt', 1)
            request.assert_not_called()

    def test_unavailable_free_model_is_rejected_before_session(self):
        with patch.object(api, 'models', return_value=[]), patch.object(api, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'exposed'):
                api.ask(api.MODELS[0], 'synthetic prompt', 1)
            request.assert_not_called()

    def test_invalid_timeout_and_empty_prompt_fail_before_network(self):
        with patch.object(api, 'request') as request:
            for timeout, prompt in [(0, 'text'), (181, 'text'), (1, '')]:
                with self.assertRaises(ValueError):
                    api.ask(api.MODELS[0], prompt, timeout)
            request.assert_not_called()

    def fake_request(self, messages=None, fail_poll=False):
        calls = []
        def request(path, body=None, timeout=5, method=None):
            calls.append((path, body))
            if path == '/session':
                return {'id': 'ses_synthetic'}
            if path == '/session/status':
                return {}
            if path.endswith('/message'):
                if fail_poll:
                    raise OSError('Synthetic transport failure')
                return copy.deepcopy(messages or [])
            return None
        return request, calls

    def test_ask_success_persists_response(self):
        request, calls = self.fake_request([assistant()])
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=request):
            self.assertEqual(api.ask(api.MODELS[0], 'synthetic prompt', 3), 0)
        result = json.loads((self.folder / 'runs/ses_synthetic/result.json').read_text())
        self.assertEqual(result['status'], 'OPENCODE_RESPONSE')
        submitted = next(body for path, body in calls if path.endswith('/prompt_async'))
        self.assertEqual(submitted['model']['providerID'], 'opencode')
        self.assertEqual(submitted['model']['modelID'], api.MODELS[0])
        self.assertFalse(submitted['tools']['bash'])

    def test_timeout_aborts_owned_session_and_persists_failure(self):
        request, calls = self.fake_request([])
        ticks = iter([0, 0, 0, 2, 2, 2])
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=request), patch.object(api.time, 'monotonic', side_effect=lambda: next(ticks, 2)), patch.object(api.time, 'sleep'):
            self.assertEqual(api.ask(api.MODELS[0], 'synthetic prompt', 1), 1)
        self.assertTrue(any(path == '/session/ses_synthetic/abort' for path, _ in calls))
        result = json.loads((self.folder / 'runs/ses_synthetic/result.json').read_text())
        self.assertEqual(result['status'], 'MODEL_TIMEOUT')

    def test_poll_error_aborts_owned_session_and_records_failure(self):
        request, calls = self.fake_request(fail_poll=True)
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=request):
            try:
                code = api.ask(api.MODELS[0], 'synthetic prompt', 1)
                self.assertNotEqual(code, 0)
            except OSError:
                pass
        self.assertTrue(any(path == '/session/ses_synthetic/abort' for path, _ in calls))
        result = json.loads((self.folder / 'runs/ses_synthetic/result.json').read_text())
        self.assertNotEqual(result['status'], 'OPENCODE_RESPONSE')

    def test_malformed_poll_envelope_aborts_and_records_diagnostic(self):
        request, calls = self.fake_request([{'info': None}])
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=request):
            self.assertEqual(api.ask(api.MODELS[0], 'synthetic prompt', 1), 1)
        self.assertTrue(any(path == '/session/ses_synthetic/abort' for path, _ in calls))
        result = json.loads((self.folder / 'runs/ses_synthetic/result.json').read_text())
        self.assertEqual(result['status'], 'MODEL_API_ERROR')
        self.assertIn('envelope', result['error'])

    def test_free_limit_aborts_owned_session_without_paid_fallback(self):
        request, calls = self.fake_request([])
        def limited(path, body=None, timeout=5, method=None):
            if path == '/session/status':
                return {'ses_synthetic': {'type': 'retry', 'action': {'reason': 'free_tier_limit'}}}
            return request(path, body, timeout, method)
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=limited):
            self.assertEqual(api.ask(api.MODELS[0], 'synthetic prompt', 3), 1)
        result = json.loads((self.folder / 'runs/ses_synthetic/result.json').read_text())
        self.assertEqual(result['status'], 'MODEL_FREE_LIMIT')
        self.assertTrue(any(path == '/session/ses_synthetic/abort' for path, _ in calls))
        self.assertEqual(sum(path == '/session' for path, _ in calls), 1)

    def test_other_sessions_free_limit_does_not_abort_them(self):
        request, calls = self.fake_request([])
        def other_limited(path, body=None, timeout=5, method=None):
            if path == '/session/status':
                return {'ses_other': {'type': 'retry', 'action': {'reason': 'free_tier_limit'}}}
            return request(path, body, timeout, method)
        ticks = iter([0, 0, 0, 2, 2, 2])
        with patch.object(api, 'models', return_value=[{'id': api.MODELS[0]}]), patch.object(api, 'request', side_effect=other_limited), patch.object(api.time, 'monotonic', side_effect=lambda: next(ticks, 2)), patch.object(api.time, 'sleep'):
            self.assertEqual(api.ask(api.MODELS[0], 'synthetic prompt', 1), 1)
        self.assertFalse(any('ses_other' in path for path, _ in calls))


if __name__ == '__main__':
    unittest.main()
