"""Create source-bound scenario plans and XML drafts. Final authority is Test-ScenarioXml.ps1."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import icd_tool

SKILL = Path(__file__).resolve().parents[1]
KINDS = ('Periodic', 'Manual', 'Response')
MAX_TIME = 2147483647


class PlanError(ValueError):
    def __init__(self, code, path, expected, observed):
        self.diagnostic = dict(code=code, path=path, expected=expected, observed=observed)
        super().__init__(code + ': ' + path)


def fail(code, path, expected, observed):
    raise PlanError(code, path, expected, observed)


def keys(value, required, optional=(), path='$'):
    if not isinstance(value, dict):
        fail('object_required', path, 'object', type(value).__name__)
    missing = sorted(set(required) - value.keys())
    extra = sorted(value.keys() - set(required) - set(optional))
    if missing or extra:
        fail('object_keys', path, {'required': list(required), 'optional': list(optional)}, {'missing': missing, 'unknown': extra})


def text(value, path):
    validator = icd_tool.Validator()
    validator.text(value, path)
    if validator.errors:
        fail('text_required', path, 'nonempty XML-compatible string', value)
    return value


def array(value, path):
    if not isinstance(value, list):
        fail('array_required', path, 'array', type(value).__name__)
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    if Path(path).stat().st_size > 32000000:
        fail('input_too_large', str(path), 'at most 32000000 bytes', 'larger file')
    return icd_tool.load_ir(path)


def load_context(path):
    context = load_json(path)
    keys(context, ('context_version', 'config_path', 'config_name', 'core_sha256', 'icds', 'sources'))
    if type(context['context_version']) is not int or context['context_version'] != 1:
        fail('context_version', '$.context_version', 1, context['context_version'])
    sources = array(context['sources'], '$.sources')
    if not sources:
        fail('sources_required', '$.sources', 'nonempty source fingerprint list', sources)
    for index, source in enumerate(sources):
        where = f'$.sources[{index}]'
        keys(source, ('path', 'sha256'), path=where)
        source_path = Path(text(source['path'], where + '.path'))
        if not source_path.is_absolute() or not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']):
            fail('source_fingerprint', where, 'absolute path and SHA-256', source)
        if not source_path.is_file() or sha(source_path) != source['sha256']:
            fail('STALE_CONTEXT', where, 'unchanged readable source; export context again', str(source_path))
    if Path(context['config_path']).resolve() not in {Path(s['path']).resolve() for s in sources}:
        fail('config_fingerprint_missing', '$.sources', 'Config fingerprint', context['config_path'])
    seen = set()
    for index, icd in enumerate(array(context['icds'], '$.icds')):
        where = f'$.icds[{index}]'
        keys(icd, ('key', 'targets', 'send', 'receive'), path=where)
        key = text(icd['key'], where + '.key')
        if key in seen:
            fail('duplicate_icd', where, 'unique exact Config key', key)
        seen.add(key)
        targets = array(icd['targets'], where + '.targets')
        if any(not isinstance(t, str) or not t.strip() for t in targets) or len(set(targets)) != len(targets):
            fail('target_catalog', where + '.targets', 'unique active link names', targets)
        for direction in ('send', 'receive'):
            codes = set()
            for message in array(icd[direction], where + '.' + direction):
                keys(message, ('code', 'name', 'id', 'length', 'body', 'user_header', 'automatic_header'), path=where)
                code = text(message['code'], where + '.code')
                if code in codes:
                    fail('duplicate_message', where, 'unique message codes', code)
                codes.add(code)
                paths = set()
                for group in ('body', 'user_header'):
                    for field in array(message[group], where + '.' + group):
                        keys(field, ('path', 'type', 'width', 'signed', 'enum', 'enum_items'), path=where)
                        name = text(field['path'], where + '.path')
                        if name in paths or type(field['width']) is not int or not 1 <= field['width'] <= 32 or type(field['signed']) is not bool:
                            fail('field_contract', where, 'unique path, width 1..32 and signed boolean', field)
                        paths.add(name)
                        items = array(field['enum_items'], where + '.enum_items')
                        item_names = set()
                        for item in items:
                            keys(item, ('name', 'value'), path=where)
                            item_name = text(item['name'], where + '.enum_items.name')
                            if item_name in item_names or type(item['value']) is not int or not 0 <= item['value'] < (1 << field['width']):
                                fail('enum_contract', where, 'unique names and values within leaf width', item)
                            item_names.add(item_name)
                auto = array(message['automatic_header'], where + '.automatic_header')
                if any(not isinstance(p, str) for p in auto) or len(set(auto)) != len(auto) or set(auto) & paths:
                    fail('header_contract', where, 'distinct automatic header names', auto)
    if not seen:
        fail('icds_required', '$.icds', 'at least one ICD', [])
    return context


def find_icd(context, key):
    for icd in context['icds']:
        if icd['key'] == key:
            return icd
    fail('unknown_icd', '$.icd', [x['key'] for x in context['icds']], key)


def find_message(icd, code, direction):
    for message in icd[direction]:
        if message['code'] == code:
            return message
    fail('message_direction', '$.' + direction, [m['code'] for m in icd[direction]], code)


def safe_output(path, extension, protected):
    resolved = Path(path).resolve()
    if resolved.suffix.lower() != extension or resolved.is_relative_to(SKILL) or resolved in {Path(p).resolve() for p in protected}:
        fail('unsafe_output', str(path), 'separate ' + extension + ' file outside Skill and input sources', str(resolved))
    return resolved


def template(context, context_path, kind, icd_key, code, name, trigger=None):
    icd = find_icd(context, icd_key)
    message = find_message(icd, code, 'send')
    if kind != 'Response' and trigger is not None:
        fail('unexpected_trigger', '$.trigger', 'only Response accepts trigger', trigger)
    entry = dict(kind=kind, name=kind + ' ' + code, icd=icd_key, message=code, targets=None,
                 values={leaf['path']: None for leaf in message['body']})
    if kind == 'Periodic':
        entry.update(period_ms=None, start_delay_ms=0, enabled=True)
    if kind == 'Response':
        find_message(icd, trigger, 'receive')
        entry.update(trigger=trigger, delay_ms=0, enabled=True, conditions={})
    return dict(schema_version=1, context_sha256=sha(context_path), name=name, unresolved=[], entries=[entry])


def validate_value(value, leaf, path):
    text(value, path)
    token = value.strip()
    if any(item['name'] == token for item in leaf['enum_items']):
        return
    hexadecimal = bool(re.fullmatch(r'0[xX][0-9a-fA-F]+', token))
    if hexadecimal:
        number = int(token[2:], 16)
    elif re.fullmatch(r'-?[0-9]+', token):
        number = int(token)
    else:
        fail('field_value', path, 'enum name, decimal integer or 0x bit pattern', value)
    width = leaf['width']
    low = -(1 << (width - 1)) if leaf['signed'] and not hexadecimal else 0
    high = (1 << (width - 1)) - 1 if leaf['signed'] and not hexadecimal else (1 << width) - 1
    if not low <= number <= high:
        fail('value_range', path, f'{low}..{high}', value)


def validate_plan(context, context_path, plan):
    keys(plan, ('schema_version', 'context_sha256', 'name', 'unresolved', 'entries'))
    if type(plan['schema_version']) is not int or plan['schema_version'] != 1:
        fail('schema_version', '$.schema_version', 1, plan['schema_version'])
    if plan['context_sha256'] != sha(context_path):
        fail('STALE_PLAN', '$.context_sha256', 'current context SHA-256; review/regenerate plan', plan['context_sha256'])
    text(plan['name'], '$.name')
    if array(plan['unresolved'], '$.unresolved'):
        fail('unresolved_facts', '$.unresolved', 'empty after requirements are established', plan['unresolved'])
    entries = array(plan['entries'], '$.entries')
    if not entries:
        fail('entries_required', '$.entries', 'at least one requested entry', [])
    omissions = []
    for index, entry in enumerate(entries):
        at = f'$.entries[{index}]'
        if not isinstance(entry, dict) or entry.get('kind') not in KINDS:
            fail('unsupported_entry', at, list(KINDS), entry)
        kind = entry['kind']
        required = ['kind', 'name', 'icd', 'message', 'targets', 'values']
        if kind == 'Periodic':
            required += ['period_ms', 'start_delay_ms']
        elif kind == 'Response':
            required += ['trigger', 'delay_ms', 'conditions']
        keys(entry, required, ('enabled',) if kind != 'Manual' else (), at)
        text(entry['name'], at + '.name')
        icd = find_icd(context, entry['icd'])
        message = find_message(icd, entry['message'], 'send')
        targets = entry['targets']
        if targets == '*':
            if not icd['targets']:
                fail('no_active_targets', at + '.targets', 'at least one active link for this ICD', targets)
        elif not isinstance(targets, list) or not targets or any(not isinstance(t, str) or t not in icd['targets'] for t in targets):
            fail('targets', at + '.targets', {'active': icd['targets'], 'wildcard': '*'}, targets)
        elif len(set(targets)) != len(targets):
            fail('duplicate_targets', at + '.targets', 'unique target names', targets)
        if 'enabled' in entry and type(entry['enabled']) is not bool:
            fail('boolean_required', at + '.enabled', 'JSON boolean', entry['enabled'])
        for prop in ('period_ms', 'start_delay_ms', 'delay_ms'):
            if prop in entry:
                minimum = 10 if prop == 'period_ms' else 0
                value = entry[prop]
                if type(value) is not int or not minimum <= value <= MAX_TIME:
                    fail('time_range', at + '.' + prop, f'JSON integer {minimum}..{MAX_TIME}', value)
        values = entry['values']
        if not isinstance(values, dict):
            fail('object_required', at + '.values', 'leaf-path to string map', values)
        required_fields = {f['path']: f for f in message['body']}
        optional_fields = {f['path']: f for f in message['user_header']}
        fields = {**required_fields, **optional_fields}
        missing = [path for path in required_fields if path not in values or values[path] is None]
        if missing:
            fail('unresolved_values', at + '.values', 'explicit value for every body leaf; no automatic zero fill', missing)
        for path, value in values.items():
            if path in message['automatic_header']:
                fail('automatic_header_forbidden', at + '.values.' + path, 'Core-owned id/length/seq', value)
            if path not in fields:
                fail('unknown_field', at + '.values', list(fields), path)
            validate_value(value, fields[path], at + '.values.' + path)
        omitted = [path for path in optional_fields if path not in values]
        if omitted:
            omissions.append({'entry': index, 'fields': omitted, 'runtime_default': '0'})
        if kind == 'Response':
            trigger = find_message(icd, entry['trigger'], 'receive')
            conditions = entry['conditions']
            if not isinstance(conditions, dict):
                fail('object_required', at + '.conditions', 'trigger body leaf to string map', conditions)
            allowed = {leaf['path']: leaf for leaf in trigger['body']}
            for path, value in conditions.items():
                if path not in allowed:
                    fail('condition_field', at + '.conditions', list(allowed), path)
                validate_value(value, allowed[path], at + '.conditions.' + path)
    return omissions


def xml_bytes(plan):
    root = ET.Element('Scenario', {'name': plan['name']})
    for kind in KINDS:
        for entry in (value for value in plan['entries'] if value['kind'] == kind):
            attrs = dict(name=entry['name'], icd=entry['icd'], message=entry['message'],
                         targets='*' if entry['targets'] == '*' else ','.join(entry['targets']))
            for source, target in (('period_ms', 'periodMs'), ('start_delay_ms', 'startDelayMs'), ('delay_ms', 'delayMs'), ('trigger', 'trigger')):
                if source in entry:
                    attrs[target] = str(entry[source])
            if 'enabled' in entry:
                attrs['enabled'] = 'true' if entry['enabled'] else 'false'
            element = ET.SubElement(root, kind, attrs)
            for field, value in entry.get('conditions', {}).items():
                ET.SubElement(element, 'Condition', dict(field=field, value=value))
            for field, value in entry['values'].items():
                ET.SubElement(element, 'Value', dict(field=field, value=value))
    ET.indent(root, space='  ')
    return b'\xef\xbb\xbf' + ('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='unicode') + '\n').replace('\n', '\r\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('catalog', 'fields', 'template', 'generate'))
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--icd')
    parser.add_argument('--message')
    parser.add_argument('--direction', choices=('send', 'receive'), default='send')
    parser.add_argument('--kind', choices=KINDS)
    parser.add_argument('--trigger')
    parser.add_argument('--name', default='Scenario draft')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        context = load_context(args.context)
        protected = [args.context, *[source['path'] for source in context['sources']]]
        if args.action == 'catalog':
            result = {'status': 'SCENARIO_CATALOG', 'icds': [{'key': i['key'], 'targets': i['targets'],
                       'send': [m['code'] for m in i['send']], 'receive': [m['code'] for m in i['receive']]} for i in context['icds']]}
        elif args.action == 'fields':
            if not args.icd or not args.message:
                parser.error('fields requires --icd and --message')
            result = {'status': 'SCENARIO_FIELDS', **find_message(find_icd(context, args.icd), args.message, args.direction)}
        elif args.action == 'template':
            if not all((args.kind, args.icd, args.message, args.output)):
                parser.error('template requires --kind, --icd, --message and --output')
            plan = template(context, args.context, args.kind, args.icd, args.message, args.name, args.trigger)
            output = safe_output(args.output, '.json', protected)
            icd_tool.atomic_write(output, (json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            result = {'status': 'SCENARIO_TEMPLATE_CREATED', 'path': str(output), 'values_unresolved': len(plan['entries'][0]['values']),
                      'defaults': 'enabled=true, delays=0; targets, period and body values must be supplied', 'scenario_core_validation': 'NOT_RUN'}
        else:
            if not args.plan or not args.output:
                parser.error('generate requires --plan and --output')
            plan = load_json(args.plan)
            omissions = validate_plan(context, args.context, plan)
            output = safe_output(args.output, '.xml', [*protected, args.plan])
            icd_tool.atomic_write(output, xml_bytes(plan))
            result = {'status': 'SCENARIO_DRAFT_CREATED', 'path': str(output), 'entries': len(plan['entries']),
                      'omitted_user_headers': omissions, 'scenario_core_validation': 'NOT_RUN'}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except PlanError as error:
        result = {'status': 'SCENARIO_INPUT_FAIL', 'errors': [error.diagnostic], 'scenario_core_validation': 'NOT_RUN'}
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as error:
        result = {'status': 'SCENARIO_INPUT_FAIL', 'errors': [{'code': 'input_error', 'message': str(error)}], 'scenario_core_validation': 'NOT_RUN'}
    print(json.dumps(result, ensure_ascii=False))
    return 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
