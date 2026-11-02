"""Scenario plans/drafts and source binding. Fake contexts here do not qualify Core/model behavior."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/udpsim-icd-authoring/scripts'))
import scenario_tool as S


def leaf(path, width=8, signed=False, items=None):
    return dict(path=path, type='int16' if signed else 'uint8', width=width, signed=signed,
                enum='Toggle' if items else None, enum_items=items or [])


class ScenarioPlans(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.config = self.work / 'Config.xml'
        self.config.write_text('synthetic unit context source', encoding='utf-8')
        self.context_path = self.work / 'context.json'
        toggles = [{'name': 'Off', 'value': 0}, {'name': 'On', 'value': 1}]
        self.body = [leaf('Count'), leaf('Groups[0].Reading', 16, True), leaf('Flags.Enabled', 1, items=toggles), leaf('Flags.Mode', 2)]
        message = dict(code='SET', name='Set', id=1, length=6, body=self.body,
                       user_header=[leaf('Sender')], automatic_header=['Id', 'Size', 'Seq'])
        receive = dict(code='STATUS', name='Status', id=2, length=4,
                       body=[leaf('Status'), leaf('Ready', 1, items=toggles)],
                       user_header=[leaf('Sender')], automatic_header=['Id', 'Size', 'Seq'])
        self.context = dict(context_version=1, config_path=str(self.config), config_name='Unit fake context', core_sha256='0'*64,
                            sources=[dict(path=str(self.config), sha256=S.sha(self.config))],
                            icds=[dict(key='device.xml', targets=['A', 'B'], send=[message], receive=[receive])])
        self.write_context()
        self.values = {'Count': '2', 'Groups[0].Reading': '-300', 'Flags.Enabled': 'On', 'Flags.Mode': '3'}
        self.plan = self.make_plan()

    def write_context(self):
        self.context_path.write_text(json.dumps(self.context), encoding='utf-8')

    def make_plan(self, kind='Manual'):
        plan = S.template(self.context, self.context_path, kind, 'device.xml', 'SET', 'Unit scenario', 'STATUS' if kind == 'Response' else None)
        plan['entries'][0]['targets'] = ['A']
        plan['entries'][0]['values'] = dict(self.values)
        if kind == 'Periodic':
            plan['entries'][0]['period_ms'] = 100
        return plan

    def error(self, code, plan=None):
        with self.assertRaises(S.PlanError) as caught:
            S.validate_plan(self.context, self.context_path, plan or self.plan)
        self.assertEqual(caught.exception.diagnostic['code'], code)

    def test_template_contains_all_expanded_paths_with_null_values(self):
        value = S.template(self.context, self.context_path, 'Manual', 'device.xml', 'SET', 'Draft')
        self.assertEqual(value['entries'][0]['values'], {f['path']: None for f in self.body})
        self.assertIsNone(value['entries'][0]['targets'])
        self.assertNotIn('Sender', value['entries'][0]['values'])

    def test_fresh_context_loads(self):
        self.assertEqual(S.load_context(self.context_path)['config_name'], 'Unit fake context')

    def test_stale_or_missing_source_rejected(self):
        self.config.write_text('changed', encoding='utf-8')
        with self.assertRaises(S.PlanError) as error:
            S.load_context(self.context_path)
        self.assertEqual(error.exception.diagnostic['code'], 'STALE_CONTEXT')
        self.config.unlink()
        with self.assertRaises(S.PlanError):
            S.load_context(self.context_path)

    def test_context_boolean_version_rejected(self):
        self.context['context_version'] = True
        self.write_context()
        with self.assertRaises(S.PlanError):
            S.load_context(self.context_path)

    def test_context_requires_config_fingerprint(self):
        other = self.work / 'other.txt'
        other.write_text('other', encoding='utf-8')
        self.context['sources'] = [dict(path=str(other), sha256=S.sha(other))]
        self.write_context()
        with self.assertRaises(S.PlanError):
            S.load_context(self.context_path)

    def test_no_guess_for_missing_or_null_value(self):
        for operation in ('remove', 'null'):
            plan = copy.deepcopy(self.plan)
            if operation == 'remove':
                del plan['entries'][0]['values']['Count']
            else:
                plan['entries'][0]['values']['Count'] = None
            self.error('unresolved_values', plan)

    def test_optional_header_omission_is_reported(self):
        self.assertEqual(S.validate_plan(self.context, self.context_path, self.plan),
                         [{'entry': 0, 'fields': ['Sender'], 'runtime_default': '0'}])
        self.plan['entries'][0]['values']['Sender'] = '7'
        self.assertEqual(S.validate_plan(self.context, self.context_path, self.plan), [])

    def test_automatic_header_cannot_be_assigned(self):
        self.plan['entries'][0]['values']['Seq'] = '9'
        self.error('automatic_header_forbidden')

    def test_path_and_case_must_match(self):
        self.plan['entries'][0]['values']['groups[0].Reading'] = '-300'
        self.error('unknown_field')

    def test_send_receive_directions_enforced(self):
        self.plan['entries'][0]['message'] = 'STATUS'
        self.error('message_direction')
        response = self.make_plan('Response')
        response['entries'][0]['trigger'] = 'SET'
        self.error('message_direction', response)

    def test_conditions_are_receive_body_only(self):
        response = self.make_plan('Response')
        response['entries'][0]['conditions'] = {'Sender': '7'}
        self.error('condition_field', response)
        response['entries'][0]['conditions'] = {'Ready': 'On'}
        S.validate_plan(self.context, self.context_path, response)

    def test_target_names_and_icd_keys_are_exact(self):
        self.plan['entries'][0]['targets'] = ['a']
        self.error('targets')
        self.plan['entries'][0]['targets'] = ['A', 'A']
        self.error('duplicate_targets')
        self.plan['entries'][0]['targets'] = []
        self.error('targets')
        self.plan['entries'][0]['targets'] = ['A']
        self.plan['entries'][0]['icd'] = 'Device.xml'
        self.error('unknown_icd')

    def test_wrong_icd_target_and_inactive_target_rejected(self):
        second = copy.deepcopy(self.context['icds'][0])
        second.update(key='other.xml', targets=['C'])
        self.context['icds'].append(second)
        for name in ('C', 'DISABLED'):
            self.plan['entries'][0]['targets'] = [name]
            self.error('targets')

    def test_wildcard_requires_active_matching_links(self):
        self.plan['entries'][0]['targets'] = '*'
        S.validate_plan(self.context, self.context_path, self.plan)
        self.context['icds'][0]['targets'] = []
        self.error('no_active_targets')

    def test_times_have_real_limits_and_types(self):
        for field, values in [('period_ms', (None, True, '100', 9, 2147483648)),
                              ('start_delay_ms', (-1, '0', False))]:
            for value in values:
                plan = self.make_plan('Periodic')
                plan['entries'][0][field] = value
                self.error('time_range', plan)
        plan = self.make_plan('Periodic')
        plan['entries'][0].update(period_ms=10, start_delay_ms=2147483647)
        S.validate_plan(self.context, self.context_path, plan)

    def test_manual_does_not_accept_period_or_enabled(self):
        for name, value in [('enabled', False), ('period_ms', 100), ('trigger', 'STATUS')]:
            plan = copy.deepcopy(self.plan)
            plan['entries'][0][name] = value
            self.error('object_keys', plan)

    def test_enabled_requires_json_boolean(self):
        plan = self.make_plan('Periodic')
        plan['entries'][0]['enabled'] = 'false'
        self.error('boolean_required', plan)

    def test_value_width_signed_hex_and_enum(self):
        values = self.plan['entries'][0]['values']
        for field, value in [('Count', '-1'), ('Count', '256'), ('Flags.Mode', '4'),
                             ('Groups[0].Reading', '32768'), ('Groups[0].Reading', '-32769')]:
            plan = copy.deepcopy(self.plan)
            plan['entries'][0]['values'][field] = value
            self.error('value_range', plan)
        for value in ('-32768', '32767', '0xffff'):
            values['Groups[0].Reading'] = value
            S.validate_plan(self.context, self.context_path, self.plan)

    def test_value_text_and_names(self):
        for value in ('on', '1e3', '+1', '0xZZ', '', 1, False, '\x00'):
            plan = copy.deepcopy(self.plan)
            plan['entries'][0]['values']['Flags.Enabled'] = value
            with self.assertRaises(S.PlanError):
                S.validate_plan(self.context, self.context_path, plan)
        self.plan['entries'][0]['values']['Flags.Enabled'] = '0x1'
        S.validate_plan(self.context, self.context_path, self.plan)

    def test_plan_bound_to_exact_context_and_unresolved(self):
        self.plan['context_sha256'] = '0'*64
        self.error('STALE_PLAN')
        self.plan['context_sha256'] = S.sha(self.context_path)
        self.plan['unresolved'] = ['period not established']
        self.error('unresolved_facts')

    def test_unknown_kind_and_root_attributes_rejected(self):
        self.plan['entries'][0]['kind'] = 'WaitThenRetry'
        self.error('unsupported_entry')
        self.plan['entries'][0]['kind'] = 'Manual'
        self.plan['extra'] = 'ignored?'
        self.error('object_keys')

    def test_duplicate_keys_and_nan_rejected(self):
        path = self.work / 'bad.json'
        for value in ('{"a":1,"a":2}', '{"a":NaN}'):
            path.write_text(value, encoding='utf-8')
            with self.assertRaises(ValueError):
                S.load_json(path)

    def test_xml_order_escape_encoding_and_literal_values(self):
        periodic, response = self.make_plan('Periodic'), self.make_plan('Response')
        self.plan['name'] = '한글 & <scenario>'
        self.plan['entries'] = [response['entries'][0], self.plan['entries'][0], periodic['entries'][0]]
        self.plan['entries'][0]['conditions'] = {'Ready': 'On'}
        S.validate_plan(self.context, self.context_path, self.plan)
        data = S.xml_bytes(self.plan)
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        root = ET.fromstring(data)
        self.assertEqual(root.attrib['name'], '한글 & <scenario>')
        self.assertEqual([child.tag for child in root], ['Periodic', 'Manual', 'Response'])
        self.assertEqual(root[-1][0].tag, 'Condition')
        self.assertEqual(root[0].find('Value').attrib['value'], '2')

    def test_output_cannot_overwrite_inputs_or_skill(self):
        for path, ext in [(self.context_path, '.json'), (self.config, '.xml'), (S.SKILL / 'bad.xml', '.xml')]:
            with self.assertRaises(S.PlanError):
                S.safe_output(path, ext, [self.config, self.context_path])

    def test_cli_failure_preserves_previous_output(self):
        output = self.work / 'scenario.xml'
        output.write_bytes(b'previous output')
        path = self.work / 'plan.json'
        self.plan['entries'][0]['values']['Count'] = None
        path.write_text(json.dumps(self.plan), encoding='utf-8')
        result = subprocess.run([sys.executable, str(Path(S.__file__)), 'generate', '--context', str(self.context_path),
                                 '--plan', str(path), '--output', str(output)], capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['errors'][0]['code'], 'unresolved_values')
        self.assertEqual(output.read_bytes(), b'previous output')


if __name__ == '__main__':
    unittest.main()
