"""Restricted synthetic-QA stdio MCP adapter. No shell or arbitrary filesystem tools."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import run_udpsim_opencode_eval as E

READ_NAMES = ('skill', 'workflow', 'contract', 'source-guide', 'pdf-guide', 'app-guide', 'app-format', 'candidate', 'checkpoint')


def schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


TOOLS = [
    {'name': 'read', 'description': 'Read the requested Skill/reference, saved candidate or checkpoint. No arbitrary paths.',
     'inputSchema': schema({'resource': {'type': 'string', 'enum': list(READ_NAMES)}}, ['resource'])},
    {'name': 'source', 'description': 'Read synthetic source. For PDF, choose physical first_page/last_page to follow dependencies.',
     'inputSchema': schema({'first_page': {'type': 'integer', 'minimum': 1}, 'last_page': {'type': 'integer', 'minimum': 1}})},
    {'name': 'save', 'description': 'Save your complete IR JSON. This invalidates earlier validation; does not claim correctness.',
     'inputSchema': schema({'definition_json': {'type': 'string'}}, ['definition_json'])},
    {'name': 'validate', 'description': 'Run actual intermediate validator on saved IR. Failure diagnostics must be corrected from source.', 'inputSchema': schema()},
    {'name': 'convert', 'description': 'Convert fresh IR_PASS candidate to XML using the real deterministic converter.', 'inputSchema': schema()},
    {'name': 'validate_xml', 'description': 'Run the actual UdpSim Core validator. Only real success creates XML_PASS checkpoint.', 'inputSchema': schema()},
    {'name': 'block', 'description': 'Persist unavailable/conflicting/unsupported source facts. No final XML is accepted.',
     'inputSchema': schema({'unresolved': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1}}, ['unresolved'])},
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Adapter:
    def __init__(self, workspace):
        self.work = Path(workspace).resolve()
        if not self.work.is_relative_to((ROOT / 'out').resolve()):
            raise ValueError('QA workspace must be under ignored out/')
        config = json.loads((self.work / 'control/config.json').read_text(encoding='utf-8'))
        self.source = self.work / config['source']
        if not self.source.resolve().is_relative_to(self.work):
            raise ValueError('Source must stay within the QA workspace')
        self.udpsim = Path(config['udpsim_root']).resolve()
        self.pause_on_ir = bool(config.get('pause_on_ir'))
        self.resources = {key: self.work / value for key, value in config['resources'].items()}
        if set(self.resources) != set(READ_NAMES) - {'candidate', 'checkpoint'}:
            raise ValueError('Unexpected resource allowlist')
        if any(not path.resolve().is_relative_to(self.work) for path in self.resources.values()):
            raise ValueError('Read resources must stay within the QA workspace')
        self.resources.update(candidate=self.work / 'candidate.json', checkpoint=self.work / 'checkpoint.json')
        self.candidate = self.work / 'candidate.json'
        self.xml = self.work / 'message.icd.xml'
        self.state = self.work / 'checkpoint.json'

    def inputs_hash(self):
        value = hashlib.sha256()
        paths = [self.source, *[path for key, path in self.resources.items() if key not in ('candidate', 'checkpoint')],
                 Path(__file__), Path(E.__file__), ROOT / 'tools/udpsim_native_qa.py',
                 E.SKILL / 'scripts/icd_tool.py', E.SKILL / 'scripts/Test-IcdXml.ps1']
        paths += sorted(p for base in ('src', 'tools/xml') for p in (self.udpsim / base).rglob('*')
                        if p.is_file() and not {'bin', 'obj'}.intersection(p.parts) and p.suffix in ('.cs', '.csproj', '.ps1'))
        for path in paths:
            value.update(str(path).encode('utf-8')); value.update(path.read_bytes())
        return value.hexdigest()

    def checkpoint(self, stage, **more):
        value = {'stage': stage, 'inputs_hash': self.inputs_hash(),
                 'candidate_hash': digest(self.candidate) if self.candidate.exists() else None,
                 'xml_hash': digest(self.xml) if stage in ('XML_WRITTEN', 'XML_PASS') and self.xml.exists() else None, **more}
        E.save(self.state, value)
        return value

    def fresh(self, stages):
        if not self.state.exists():
            raise ValueError('No saved checkpoint; validate the candidate first')
        value = json.loads(self.state.read_text(encoding='utf-8'))
        if value.get('inputs_hash') != self.inputs_hash():
            raise ValueError('STALE_CHECKPOINT: source, Skill or tool implementation changed')
        if value.get('candidate_hash') != (digest(self.candidate) if self.candidate.exists() else None):
            raise ValueError('STALE_CHECKPOINT: candidate changed')
        if value.get('stage') not in stages:
            raise ValueError('Required checkpoint stage: ' + ','.join(stages))
        if value.get('stage') in ('XML_WRITTEN', 'XML_PASS') and value.get('xml_hash') != (digest(self.xml) if self.xml.exists() else None):
            raise ValueError('STALE_CHECKPOINT: XML changed')
        return value

    def run(self, args, label):
        folder = self.work / 'commands'
        folder.mkdir(exist_ok=True)
        index = len(list(folder.glob('*.json'))) + 1
        return E.command(args, folder, f'{index:03d}-{label}')

    def invoke(self, name, arguments):
        tool = next((item for item in TOOLS if item['name'] == name), None)
        if tool is None or not isinstance(arguments, dict):
            raise ValueError('Unknown tool or invalid arguments')
        declared = tool['inputSchema']
        if set(arguments) - set(declared['properties']) or set(declared['required']) - set(arguments):
            raise ValueError('Unknown or missing tool arguments')
        if name == 'read':
            resource = arguments['resource']
            if resource not in READ_NAMES:
                raise ValueError('Resource is not allowlisted')
            if resource == 'checkpoint':
                return self.fresh(('CANDIDATE', 'IR_FAIL', 'IR_PASS', 'XML_WRITTEN', 'XML_PASS', 'BLOCKED'))
            path = self.resources[resource]
            if not path.is_file() or path.stat().st_size > 1_000_000:
                raise ValueError('Requested resource is absent or too large')
            return {'resource': resource, 'text': path.read_text(encoding='utf-8-sig')}
        if name == 'source':
            if self.source.suffix.lower() == '.pdf':
                from pypdf import PdfReader
                pages = PdfReader(self.source).pages
                first, last = arguments.get('first_page', 1), arguments.get('last_page', len(pages))
                if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(pages):
                    raise ValueError('Invalid physical PDF page range')
                return {'source': self.source.name, 'page_count': len(pages), 'first_page': first, 'last_page': last,
                        'text': '\n\n'.join(f'[PHYSICAL PDF PAGE {i+1}]\n' + pages[i].extract_text() for i in range(first-1, last))}
            if arguments:
                raise ValueError('Page arguments apply only to PDF')
            return {'source': self.source.name, 'text': self.source.read_text(encoding='utf-8-sig')}
        if name == 'save':
            text = arguments['definition_json']
            if not isinstance(text, str) or len(text) > 1_000_000:
                raise ValueError('Definition must be a JSON string of at most 1000000 characters')
            definition = E.strict_json(text)
            if not isinstance(definition, dict):
                raise ValueError('Definition must be an object')
            E.save(self.candidate, definition)
            if self.xml.exists():
                self.xml.unlink()
            return self.checkpoint('CANDIDATE')
        if name == 'validate':
            budget_path = self.work / 'control/validation-budget.json'
            inputs = self.inputs_hash()
            budget = json.loads(budget_path.read_text(encoding='utf-8')) if budget_path.exists() else {}
            if budget.get('inputs_hash') != inputs:
                budget = {'inputs_hash': inputs, 'failed_candidates': []}
            if len(budget['failed_candidates']) >= 4:
                self.checkpoint('BLOCKED', unresolved=['repair limit reached: initial candidate plus three correction rounds'])
                raise ValueError('REPAIR_LIMIT: initial candidate plus three correction rounds exhausted; stop and report diagnostics')
            result = self.run([sys.executable, E.SKILL / 'scripts/icd_tool.py', 'validate', '--input', self.candidate], 'validate')
            state = self.checkpoint('IR_PASS' if result['exit_code'] == 0 and 'IR_PASS' in result['stdout'] else 'IR_FAIL')
            if state['stage'] == 'IR_FAIL' and self.candidate.exists():
                candidate_hash = digest(self.candidate)
                if candidate_hash not in budget['failed_candidates']:
                    budget['failed_candidates'].append(candidate_hash)
                E.save(budget_path, budget)
            if state['stage'] == 'IR_PASS' and self.pause_on_ir and not (self.work / 'control/resumed.flag').exists():
                (self.work / 'control/pause.flag').write_text('IR_PASS checkpoint persisted', encoding='utf-8')
            return {'status': state['stage'], **result}
        if name == 'convert':
            if (self.work / 'control/pause.flag').exists():
                raise ValueError('CONTROLLED_PAUSE: test runner will resume from the saved checkpoint')
            self.fresh(('IR_PASS', 'XML_WRITTEN', 'XML_PASS'))
            result = self.run([sys.executable, E.SKILL / 'scripts/icd_tool.py', 'convert', '--input', self.candidate, '--output', self.xml], 'convert')
            if result['exit_code'] != 0 or not self.xml.exists():
                raise ValueError('Conversion failed: ' + result['stdout'] + result['stderr'])
            state = self.checkpoint('XML_WRITTEN')
            return {'status': state['stage'], **result}
        if name == 'validate_xml':
            self.fresh(('XML_WRITTEN', 'XML_PASS'))
            result = self.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                               E.SKILL / 'scripts/Test-IcdXml.ps1', '-UdpSimRoot', self.udpsim, '-IcdPath', self.xml], 'core')
            ok = result['exit_code'] == 0 and 'XML_PASS' in result['stdout']
            self.checkpoint('XML_PASS' if ok else 'XML_WRITTEN')
            return {'status': 'XML_PASS' if ok else 'XML_FAIL', **result}
        if name == 'block':
            facts = arguments['unresolved']
            if not isinstance(facts, list) or not facts or not all(isinstance(item, str) and item.strip() for item in facts):
                raise ValueError('Name nonempty unresolved facts')
            if self.xml.exists():
                self.xml.unlink()
            return self.checkpoint('BLOCKED', unresolved=facts)
        raise ValueError('Unreachable tool')

    def call(self, name, arguments):
        try:
            value = self.invoke(name, arguments)
            failed = value.get('status') in ('IR_FAIL', 'XML_FAIL')
        except (ValueError, KeyError, TypeError, OSError) as error:
            value, failed = {'status': 'TOOL_ERROR', 'error': str(error)}, True
        phase_path = self.work / 'control/phase.txt'
        event = {'time': datetime.now(timezone.utc).isoformat(), 'phase': phase_path.read_text(encoding='utf-8') if phase_path.exists() else 'single',
                 'tool': name, 'arguments': arguments,
                 'result': value, 'isError': failed}
        with (self.work / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': failed}


def serve(adapter):
    for raw in sys.stdin.buffer:
        request_id = None
        try:
            if len(raw) > 1_100_000:
                raise ValueError('MCP request exceeds size limit')
            message = json.loads(raw)
            request_id = message.get('id')
            if 'id' not in message:
                continue
            method = message.get('method')
            params = message.get('params') or {}
            if method == 'initialize':
                version = params.get('protocolVersion')
                version = version if version in ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25') else '2025-06-18'
                result = {'protocolVersion': version, 'capabilities': {'tools': {}},
                          'serverInfo': {'name': 'udpsim-synthetic-qa', 'version': '1.0.0'}}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                result = adapter.call(params['name'], params.get('arguments') or {})
            elif method == 'ping':
                result = {}
            else:
                raise ValueError('Unsupported MCP method')
            response = {'jsonrpc': '2.0', 'id': request_id, 'result': result}
        except (ValueError, KeyError, TypeError) as error:
            response = {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32602, 'message': str(error)}}
        sys.stdout.buffer.write((json.dumps(response, ensure_ascii=False) + '\n').encode('utf-8'))
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    serve(Adapter(parser.parse_args().workspace))
