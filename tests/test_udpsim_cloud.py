"""Synthetic protocol/fault cases; no cloud credentials or external model calls."""
from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("udpsim_cloud_probe", ROOT / "tools/Test-UdpSimCloud.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def message(tool=False):
    content = [{"type": "thinking", "thinking": "synthetic", "signature": "mock-signature"}]
    content.append({"type": "tool_use", "id": "mock-tool-1", "name": "echo_probe", "input": {"value": 7}}
                   if tool else {"type": "text", "text": "QA_MOCK_OK"})
    return {"type": "message", "model": "udpsim-mock", "content": content,
            "stop_reason": "tool_use" if tool else "end_turn"}


def sse():
    events = [
        {"type": "message_start", "message": {"type": "message", "content": []}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "synthetic"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "tool_use", "id": "mock-tool-1", "name": "echo_probe", "input": {}}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"val'}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": 'ue":7}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}},
        {"type": "message_stop"},
    ]
    return "".join("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n" for event in events)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, body, code=200, content_type="application/json"):
        raw = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_GET(self):
        if self.server.scenario == "http500":
            return self.reply({"error": "synthetic"}, 500)
        if self.server.scenario == "redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.invalid/do-not-follow")
            self.end_headers()
            return
        if self.server.scenario == "badjson":
            return self.reply("{broken")
        if self.server.scenario == "missingmodel":
            return self.reply({"data": []})
        return self.reply({"data": [{"id": "udpsim-mock"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.server.scenario == "timeout":
            time.sleep(0.1)
        if self.path.endswith("count_tokens"):
            return self.reply({"input_tokens": True if self.server.scenario == "badcount" else 10})
        if body.get("stream"):
            return self.reply(sse(), content_type="text/event-stream")
        reply = message(bool(body.get("tools")))
        if self.server.scenario == "texttool" and body.get("tools"):
            reply = message(False)
            reply["content"][-1]["text"] = '{"name":"echo_probe","input":{"value":7}}'
        if self.server.scenario == "wrongtool" and body.get("tools"):
            reply["content"][-1]["input"] = {"value": 8}
        return self.reply(reply)


class CloudProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/anthropic"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.server.scenario = "good"
        self.env = patch.dict(os.environ, {"UDPSIM_GATEWAY_TOKEN": "synthetic-token",
                                          "UDPSIM_CLOUD_FREE_QUOTA_CONFIRMED": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_mock(self, stream=False, timeout=1):
        return probe.run_probe(self.base, "udpsim-mock", timeout, False, stream)

    def test_mock_positive(self):
        report = self.run_mock()
        self.assertEqual(report["status"], "GATEWAY_MOCK_PASS")
        self.assertEqual(len(report["checks"]), 4)
        self.assertEqual(report["internal_target_qa"], "NOT_RUN")

    def test_stream_positive(self):
        self.assertEqual(self.run_mock(True)["checks"][-1], "streamed_native_tool_use")

    def test_mock_external_refused(self):
        report = probe.run_probe("https://example.invalid/anthropic", "udpsim-mock", 1, False, False)
        self.assertEqual(report["error"], "MOCK_REQUIRES_LOOPBACK_GATEWAY")

    def test_mock_real_model_refused(self):
        report = probe.run_probe(self.base, "qwen3.6-27b", 1, False, False)
        self.assertEqual(report["error"], "MOCK_REQUIRES_UDPSIM_MOCK_MODEL")

    def test_live_quota_required(self):
        report = probe.run_probe(self.base, "qwen3.6-27b", 1, True, False)
        self.assertEqual(report["error"], "CONFIRM_FREE_QUOTA_ONLY_BEFORE_LIVE")

    def test_timeout(self):
        self.server.scenario = "timeout"
        self.assertEqual(self.run_mock(timeout=0.01)["error"], "TIMEOUT")

    def test_http_error_sanitized(self):
        self.server.scenario = "http500"
        self.assertEqual(self.run_mock()["error"], "HTTP_500")

    def test_redirect_not_followed(self):
        self.server.scenario = "redirect"
        self.assertEqual(self.run_mock()["error"], "HTTP_302")

    def test_invalid_json(self):
        self.server.scenario = "badjson"
        self.assertEqual(self.run_mock()["error"], "INVALID_JSON_RESPONSE")

    def test_missing_model(self):
        self.server.scenario = "missingmodel"
        self.assertEqual(self.run_mock()["error"], "REQUESTED_MODEL_NOT_LISTED")

    def test_bool_token_count_refused(self):
        self.server.scenario = "badcount"
        self.assertEqual(self.run_mock()["error"], "INVALID_INPUT_TOKEN_COUNT")

    def test_text_json_not_native_tool(self):
        self.server.scenario = "texttool"
        self.assertEqual(self.run_mock()["error"], "NATIVE_TOOL_USE_MISSING")

    def test_wrong_tool_argument(self):
        self.server.scenario = "wrongtool"
        self.assertEqual(self.run_mock()["error"], "NATIVE_TOOL_ARGUMENT_MISMATCH")

    def test_sse_truncation(self):
        with self.assertRaisesRegex(probe.ProbeError, "SSE_TRUNCATED"):
            probe.parse_sse('data: {"type":"message_start"}\n\n')

    def test_sse_error(self):
        with self.assertRaisesRegex(probe.ProbeError, "SSE_ERROR_EVENT"):
            probe.parse_sse('data: {"type":"error"}\n\n')

    def test_sse_missing_block_stop(self):
        stream = sse().replace('event: content_block_stop\ndata: {"type": "content_block_stop", "index": 1}\n\n', '')
        with self.assertRaisesRegex(probe.ProbeError, "SSE_OPEN_OR_MISSING_BLOCKS"):
            probe.parse_sse(stream)

    def test_sse_missing_message_start(self):
        stream = sse().split('\n\n', 1)[1]
        with self.assertRaisesRegex(probe.ProbeError, "SSE_INVALID_BLOCK_START"):
            probe.parse_sse(stream)

    def test_prefixed_model_listing(self):
        with patch.object(probe, "http_call", side_effect=[
                {"data": [{"id": "openai/udpsim-mock"}]}, {"input_tokens": 10}, message(), message(True)]):
            self.assertEqual(self.run_mock()["status"], "GATEWAY_MOCK_PASS")

    def test_sse_invalid_tool_json(self):
        with self.assertRaisesRegex(probe.ProbeError, "SSE_INVALID_TOOL_JSON"):
            probe.parse_sse(sse().replace('ue\\\":7}', 'ue\\\":7'))

    def test_nonstring_text_refused(self):
        with self.assertRaisesRegex(probe.ProbeError, "INVALID_TEXT_BLOCK"):
            probe.text_reply({"type": "message", "content": [{"type": "text", "text": 9}]})

    def test_report_source_overwrite_refused(self):
        with self.assertRaisesRegex(probe.ProbeError, "REPORT_MUST_BE_UNDER_IGNORED_OUT"):
            probe.safe_report_path(str(ROOT / "tools/report.json"))

    def test_no_credentials_in_report(self):
        report = json.dumps(self.run_mock())
        self.assertNotIn("synthetic-token", report)
        self.assertNotIn(self.base, report)

    def test_failure_replaces_stale_report(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "out", prefix="probe-test-") as folder:
            report = Path(folder) / "report.json"
            report.write_text('{"status":"GATEWAY_MOCK_PASS"}')
            exit_code = probe.main(["--mock", "--base-url", self.base, "--model", "qwen3.6-27b", "--report", str(report)])
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(report.read_text())["status"], "PROBE_FAIL")


if __name__ == "__main__":
    unittest.main()
