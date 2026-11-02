"""Evaluator guards; these tests do not call cloud models."""
import importlib.util
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('opencode_eval', Path(__file__).with_name('run_udpsim_opencode_eval.py'))
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


class EvaluatorTests(unittest.TestCase):
    def test_plain_and_fenced_json(self):
        for text in ('{"a":1}', '```json\n{"a":1}\n```'):
            self.assertEqual(E.strict_json(text), {'a': 1})

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            E.strict_json('{"a":1,"a":2}')

    def test_nonfinite_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.assertRaises(ValueError):
                E.strict_json('{"a":' + token + '}')

    def test_prose_not_silently_extracted(self):
        with self.assertRaises(ValueError):
            E.strict_json('Here is the answer: {"a":1}')

    def test_wrong_wire_fact_fails(self):
        self.assertTrue(E.compare({'id': 103}, {'id': 104}))

    def test_order_and_type_preserved(self):
        self.assertTrue(E.compare([1, 2], [2, 1]))
        self.assertTrue(E.compare(1, True))
        self.assertTrue(E.compare([1], [1, 2]))

    def test_provenance_allowed(self):
        self.assertEqual(E.compare({'id': 1}, {'id': 1, 'evidence': []}), [])

    def test_missing_fact_block(self):
        self.assertTrue(E.blocked({'status': 'BLOCKED', 'unresolved': ['endian unspecified']}, ['endian']))
        self.assertTrue(E.blocked({'status': 'BLOCKED', 'unresolved': ['wire byte order']}, ['endian']))

    def test_guessed_endian_rejected(self):
        self.assertFalse(E.blocked({'status': 'BLOCKED', 'unresolved': ['endian little assumed']}, ['endian']))
        self.assertFalse(E.blocked({'status': 'BLOCKED', 'unresolved': ['endian missing'], 'endian': 'big'}, ['endian']))

    def test_conflict_may_name_both_wire_orders(self):
        self.assertTrue(E.blocked({'status': 'BLOCKED', 'unresolved': ['endian conflict: big versus little']}, ['endian']))

    def test_priority_block_reason_synonyms(self):
        reasons = [('conflict', 'The documents contradict each other'), ('layout', 'Compiler padding is unknown'),
                   ('variable', 'Dynamic packet array is unsupported'), ('authority', 'Document precedence is unspecified')]
        for fact, reason in reasons:
            self.assertTrue(E.blocked({'status': 'BLOCKED', 'unresolved': [reason]}, [fact]))

    def test_vague_or_empty_block_rejected(self):
        for value in ({'status': 'BLOCKED', 'unresolved': []}, {'status': 'BLOCKED', 'unresolved': ['unknown']},
                      {'status': 'BLOCKED', 'unresolved': [{'endian': None}]}):
            self.assertFalse(E.blocked(value, ['endian']))

    def test_actual_pdf_dependency_extraction(self):
        case = {'input': 'document.pdf'}
        text = E.source_text(case)
        for expected in ('[PHYSICAL PDF PAGE 1]', '[PHYSICAL PDF PAGE 2]', '[PHYSICAL PDF PAGE 3]', 'RunState', 'SET_WINDOW'):
            self.assertIn(expected, text)

    def test_oracle_stays_out_of_prompt(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        prompt = E.prompt_for(case)
        self.assertNotIn(case['payload_hex'], prompt)
        self.assertNotIn('expected_values', prompt)
        self.assertIn('SCAN_REPORT', prompt)

    def test_unused_source_header_is_not_a_wire_error(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['types'].append(copy.deepcopy(case['optional_source_types'][0]))
        actual['types'].reverse()
        actual['enums'][0]['items'].reverse()
        self.assertEqual(E.semantic_compare(case, actual), [])

    def test_extra_header_must_match_source(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['types'].append(copy.deepcopy(case['optional_source_types'][0]))
        actual['types'][-1]['fields'][0]['type'] = 'uint32'
        self.assertTrue(E.semantic_compare(case, actual))
        actual['types'][-1] = copy.deepcopy(case['optional_source_types'][0])
        actual['types'][-1]['fields'][0]['count'] = 2
        self.assertTrue(E.semantic_compare(case, actual))

    def test_arbitrary_extra_type_still_rejected(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['types'].append({'name': 'Invented', 'fields': [{'name': 'A', 'type': 'uint8'}]})
        self.assertTrue(E.semantic_compare(case, actual))

    def test_field_order_remains_wire_fact(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['types'][0]['fields'].reverse()
        self.assertTrue(E.semantic_compare(case, actual))

    def test_extra_semantic_attribute_rejected(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['types'][0]['fields'][0]['enum'] = 'Toggle'
        self.assertTrue(E.semantic_compare(case, actual))

    def test_valid_evidence_and_root_display_name_do_not_change_semantics(self):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][0]
        actual = copy.deepcopy(case['expected'])
        actual['name'] = 'Display title'
        actual['types'][0]['fields'][0]['evidence'] = [{'source': 'scan-report.h', 'locator': 'struct Slot'}]
        self.assertEqual(E.semantic_compare(case, actual), [])

    def prepare_replay(self, root):
        case = json.loads((E.FIXTURES / 'cases.json').read_text(encoding='utf-8'))['cases'][2]
        model = E.MODELS[0]
        previous = root / 'previous' / model / case['id'] / '1'
        unit = previous / 'attempt-1'
        unit.mkdir(parents=True)
        (unit / 'prompt.txt').write_text(E.prompt_for(case), encoding='utf-8')
        E.save(previous / 'result.json', {'fingerprint': 'generation-hash'})
        envelope = {'status': 'OPENCODE_RESPONSE', 'text': '{"status":"BLOCKED","unresolved":["endian missing"]}'}
        E.save(unit / 'model.json', {'exit_code': 0, 'stdout': json.dumps(envelope), 'stderr': ''})
        args = SimpleNamespace(work_dir=root / 'rejudged', replay_from=root / 'previous', resume=False,
                               udpsim_root=None, max_attempts=3, timeout=1)
        return case, model, args, unit

    def test_replay_uses_recording_without_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            case, model, args, _ = self.prepare_replay(Path(temp))
            with patch.object(E, 'command', side_effect=AssertionError('Unexpected process/model call')):
                result = E.evaluate(model, case, 1, args, 'new-evaluator-hash')
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['generation_fingerprint'], 'generation-hash')

    def test_replay_rejects_changed_source_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            case, model, args, unit = self.prepare_replay(Path(temp))
            (unit / 'prompt.txt').write_text('Different source facts', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'unchanged source'):
                E.evaluate(model, case, 1, args, 'new-evaluator-hash')


if __name__ == '__main__':
    unittest.main()
