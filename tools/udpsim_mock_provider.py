"""Synthetic OpenAI-compatible upstream for real Bifrost/Claude transport QA."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import time
from urllib.parse import urlsplit

MODEL = 'udpsim-mock'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, body, status=200):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        print('GET ' + self.path, flush=True)
        if urlsplit(self.path).path.rstrip('/') in ('/v1/models', '/models'):
            self.send_json({'object': 'list', 'data': [{'id': MODEL, 'object': 'model', 'created': 0, 'owned_by': 'synthetic-qa'}]})
        elif self.path == '/health':
            self.send_json({'status': 'ok', 'mode': 'synthetic'})
        else:
            self.send_json({'error': {'message': 'Synthetic upstream: route not implemented'}}, 404)

    def do_POST(self):
        print('POST ' + self.path, flush=True)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > 4_000_000:
                return self.send_json({'error': {'message': 'Synthetic input too large'}}, 413)
            body = json.loads(self.rfile.read(length))
            if self.path.endswith('/count_tokens') or self.path.endswith('/responses/input_tokens'):
                return self.send_json({'input_tokens': 32})
            if self.path.endswith('/messages'):
                return self.anthropic(body)
            if not self.path.endswith('/chat/completions'):
                return self.send_json({'error': {'message': 'Synthetic route unsupported'}}, 404)
            tools = body.get('tools', [])
            names = [t.get('function', {}).get('name') for t in tools]
            messages = body.get('messages', [])
            has_result = any(m.get('role') == 'tool' for m in messages)
            call = None
            if 'echo_probe' in names:
                call = {'id': 'call_synthetic_probe', 'type': 'function', 'function': {'name': 'echo_probe', 'arguments': '{"value":7}'}}
            elif 'Read' in names and not has_result and 'CLOUD_QA_READ_FIXTURE' in json.dumps(messages):
                fixture = str(Path(__file__).resolve().parents[1] / 'tests/fixtures/udpsim-model/ping.h')
                call = {'id': 'call_synthetic_read', 'type': 'function', 'function': {'name': 'Read', 'arguments': json.dumps({'file_path': fixture})}}
            message = {'role': 'assistant', 'content': 'QA_MOCK_OK' if not call else None}
            if call:
                message['tool_calls'] = [call]
            finish = 'tool_calls' if call else 'stop'
            common = {'id': 'chatcmpl-synthetic-qa', 'created': int(time.time()), 'model': MODEL}
            if not body.get('stream'):
                return self.send_json({**common, 'object': 'chat.completion', 'choices': [{'index': 0, 'message': message, 'finish_reason': finish}], 'usage': {'prompt_tokens': 32, 'completion_tokens': 12, 'total_tokens': 44}})
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()

            def chunk(delta, reason=None):
                event = {**common, 'object': 'chat.completion.chunk', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}
                self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())
                self.wfile.flush()

            chunk({'role': 'assistant'})
            chunk({'reasoning_content': 'Synthetic transport check.'})
            if call:
                args = call['function']['arguments']
                chunk({'tool_calls': [{'index': 0, 'id': call['id'], 'type': 'function', 'function': {'name': call['function']['name'], 'arguments': args[:5]}}]})
                chunk({'tool_calls': [{'index': 0, 'function': {'arguments': args[5:]}}]})
            else:
                chunk({'content': 'QA_MOCK_OK'})
            chunk({}, finish)
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
        except (ValueError, KeyError, TypeError):
            self.send_json({'error': {'message': 'Invalid synthetic request'}}, 400)

    def anthropic(self, body):
        names = [tool.get('name') for tool in body.get('tools', [])]
        messages = body.get('messages', [])
        results = [c for m in messages if isinstance(m.get('content'), list) for c in m['content'] if isinstance(c, dict) and c.get('type') == 'tool_result']
        tool_result = bool(results)
        read_verified = False
        if tool_result:
            read_verified = any(c.get('tool_use_id') == 'toolu_mock_read' and not c.get('is_error') and 'struct Ping {' in json.dumps(c.get('content')) for c in results)
            verified = read_verified
            print('READ_FIXTURE_VERIFIED' if verified else 'TOOL_RESULT_RECEIVED', flush=True)
        block = {'type': 'text', 'text': 'QA_MOCK_OK'}
        reason = 'end_turn'
        if 'echo_probe' in names:
            block = {'type': 'tool_use', 'id': 'toolu_mock_probe', 'name': 'echo_probe', 'input': {'value': 7}}
            reason = 'tool_use'
        elif 'Read' in names and not tool_result and 'CLOUD_QA_READ_FIXTURE' in json.dumps(messages):
            fixture = str(Path(__file__).resolve().parents[1] / 'tests/fixtures/udpsim-model/ping.h')
            block = {'type': 'tool_use', 'id': 'toolu_mock_read', 'name': 'Read', 'input': {'file_path': fixture}}
            reason = 'tool_use'
        elif 'Read' in names and tool_result and not read_verified:
            block = {'type': 'text', 'text': 'QA_MOCK_READ_FAIL'}
        message = {'id': 'msg_mock_probe', 'type': 'message', 'role': 'assistant', 'model': MODEL, 'content': [block], 'stop_reason': reason, 'stop_sequence': None, 'usage': {'input_tokens': 32, 'output_tokens': 12}}
        if not body.get('stream'):
            return self.send_json(message)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        def event(name, data):
            self.wfile.write(('event: ' + name + '\ndata: ' + json.dumps(data) + '\n\n').encode())
            self.wfile.flush()

        event('message_start', {'type': 'message_start', 'message': {**message, 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 32, 'output_tokens': 0}}})
        event('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': ''}})
        event('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': 'Synthetic protocol test.'}})
        event('content_block_delta', {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'mock-signature-01'}})
        event('content_block_stop', {'type': 'content_block_stop', 'index': 0})
        if block['type'] == 'tool_use':
            event('content_block_start', {'type': 'content_block_start', 'index': 1, 'content_block': {**block, 'input': {}}})
            args = json.dumps(block['input'])
            for piece in (args[:5], args[5:]):
                event('content_block_delta', {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'input_json_delta', 'partial_json': piece}})
        else:
            event('content_block_start', {'type': 'content_block_start', 'index': 1, 'content_block': {'type': 'text', 'text': ''}})
            event('content_block_delta', {'type': 'content_block_delta', 'index': 1, 'delta': {'type': 'text_delta', 'text': block['text']}})
        event('content_block_stop', {'type': 'content_block_stop', 'index': 1})
        event('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': reason, 'stop_sequence': None}, 'usage': {'output_tokens': 12}})
        event('message_stop', {'type': 'message_stop'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18082)
    args = parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
