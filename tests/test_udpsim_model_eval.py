"""Deterministic harness tests; the HTTP server is fake, never a model qualifier."""
import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("model_eval", Path(__file__).with_name("run_udpsim_model_eval.py"))
EVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVAL)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if self.path == "/slow":
            time.sleep(.15)
        data = {"model": "fake-protocol-fixture", "message": {"content": "{}"}}
        status = 200
        if self.path == "/error":
            status, data = 500, {"error": {"message": "synthetic failure"}}
        elif self.path == "/overflow":
            status, data = 500, {"error": {"message": "maximum context length is 262144 tokens"}}
        elif self.path == "/thinking":
            data = {"model": "fake-protocol-fixture", "content": [
                {"type": "thinking", "thinking": "not JSON", "signature": "synthetic"},
                {"type": "text", "text": "{\"ok\":true}"}]}
        elif self.path == "/tool":
            data = {"content": [{"type": "thinking", "thinking": "..."},
                                {"type": "tool_use", "id": "fake", "name": "Read", "input": {}}]}
        elif self.path == "/openai":
            data = {"model": "fake-protocol-fixture", "choices": [{"message": {"content": "{}"}}]}
        elif self.path == "/bad":
            data = {"message": {"content": None}}
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        try:
            self.wfile.write(json.dumps(data).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class ModelEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.requests = []
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    def setUp(self):
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()

    def tearDown(self):
        self.redirect.__exit__(None, None, None)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_ollama_json(self):
        text, model = EVAL.request_model(self.url + "/ok", "fake", [], 1)
        self.assertEqual(json.loads(text), {})
        self.assertEqual(model, "fake-protocol-fixture")

    def test_anthropic_thinking_first_is_not_output(self):
        text, _ = EVAL.request_model(self.url + "/thinking", "fake", [{"role": "system", "content": "rules"}], 1, "anthropic")
        self.assertEqual(json.loads(text), {"ok": True})
        sent = self.server.requests[-1]
        self.assertEqual(sent["system"], "rules")
        self.assertEqual(sent["messages"], [])

    def test_tool_use_not_falsely_read_as_text(self):
        with self.assertRaisesRegex(RuntimeError, "UNEXPECTED_TOOL_USE"):
            EVAL.request_model(self.url + "/tool", "fake", [], 1, "anthropic")

    def test_openai_envelope(self):
        text, _ = EVAL.request_model(self.url + "/openai", "fake", [], 1, "openai")
        self.assertEqual(json.loads(text), {})

    def test_http_failure(self):
        with self.assertRaisesRegex(RuntimeError, "MODEL_HTTP_500"):
            EVAL.request_model(self.url + "/error", "fake", [], 1)

    def test_context_overflow_500_classified(self):
        with self.assertRaisesRegex(RuntimeError, "CONTEXT_OVERFLOW_HTTP_500"):
            EVAL.request_model(self.url + "/overflow", "fake", [], 1)

    def test_timeout(self):
        with self.assertRaisesRegex(RuntimeError, "MODEL_TIMEOUT"):
            EVAL.request_model(self.url + "/slow", "fake", [], .02)

    def test_bad_envelope(self):
        with self.assertRaisesRegex(RuntimeError, "MODEL_BAD_CONTENT"):
            EVAL.request_model(self.url + "/bad", "fake", [], 1)

    def test_ir_not_object_rejected(self):
        with self.assertRaisesRegex(ValueError, "IR_ROOT_NOT_OBJECT"):
            EVAL.parse_ir("[]")

    def test_duplicate_json_keys_rejected_before_canonicalization(self):
        with self.assertRaisesRegex(ValueError, "IR_DUPLICATE_KEY"):
            EVAL.parse_ir('{"endian":"big","endian":"little"}')
        with self.assertRaisesRegex(ValueError, "IR_DUPLICATE_KEY"):
            EVAL.parse_ir('{"messages":[{"id":1,"id":2}]}')

    def test_nonfinite_json_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant), self.assertRaisesRegex(ValueError, "IR_NONFINITE_NUMBER"):
                EVAL.parse_ir('{"id":' + constant + '}')

    def test_oracle_checks_source_facts_after_structural_pass(self):
        expected = {"requires_stop": False, "facts": {"endian": "little"}}
        self.assertFalse(EVAL.check_outcome(expected, {"endian": "big", "unresolved": []}, 0)[0])
        self.assertTrue(EVAL.check_outcome(expected, {"endian": "little", "unresolved": []}, 0)[0])

    def test_ambiguity_requires_stop_without_guess(self):
        expected = {"requires_stop": True, "missing_fact": "endian"}
        ir = {"endian": None, "unresolved": ["endian is unspecified"]}
        self.assertTrue(EVAL.check_outcome(expected, ir, 1)[0])
        self.assertFalse(EVAL.check_outcome(expected, ir, 0)[0])
        self.assertFalse(EVAL.check_outcome(expected, {**ir, "endian": "little"}, 1)[0])

    def test_numeric_bool_does_not_match_integer_oracle(self):
        self.assertTrue(EVAL.subset_errors({"id": 1}, {"id": True}))

    def test_atomic_state_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            EVAL.save_json(path, {"fixture": "한글"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"fixture": "한글"})
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def minimal_ir(self):
        return {"schema_version": 1, "name": "Synthetic", "endian": "little",
                "evidence": [{"source": "ping.h", "locator": "lines 2-6"}], "unresolved": [],
                "enums": [], "types": [],
                "header": [{"name": "Id", "type": "uint8", "role": "id"},
                           {"name": "Length", "type": "uint8", "role": "length"}],
                "messages": [{"direction": "send", "code": "PING", "id": 17,
                              "name": "Ping", "length": 3, "fields": [{"name": "Value", "type": "uint8"}]}]}

    def args(self, directory, **changes):
        args = {"case": "source", "model": "fake-fixture-only", "provider": "ollama",
                "mode": "baseline", "work_dir": directory, "timeout": 1, "max_attempts": 3,
                "resume": False}
        args.update(changes)
        return SimpleNamespace(**args)

    def test_actual_validator_feedback_repairs_then_resume_no_new_calls(self):
        out = EVAL.ROOT / "out"
        out.mkdir(exist_ok=True)
        correct = self.minimal_ir()
        wrong = copy.deepcopy(correct)
        wrong["messages"][0]["length"] = 4
        with tempfile.TemporaryDirectory(dir=out) as directory:
            args = self.args(directory)
            with patch.object(EVAL, "request_model", side_effect=[(json.dumps(wrong), "fake"), (json.dumps(correct), "fake")]) as model:
                self.assertEqual(EVAL.run(args), 0)
                self.assertEqual(model.call_count, 2)
            state = json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
            self.assertNotEqual(state["attempts"][0]["validator_exit"], 0)
            self.assertEqual(state["attempts"][1]["validator_exit"], 0)
            self.assertEqual(state["target_model_status"], "NOT_RUN")
            feedback = [m["content"] for m in state["messages"] if m["role"] == "user"][-1]
            self.assertIn("Validator output", feedback)
            self.assertNotIn("oracle_errors", feedback)
            args.resume = True
            with patch.object(EVAL, "request_model") as model:
                self.assertEqual(EVAL.run(args), 0)
                model.assert_not_called()

    def test_network_failure_stops_at_attempt_budget(self):
        out = EVAL.ROOT / "out"
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as directory:
            with patch.object(EVAL, "request_model", side_effect=RuntimeError("MODEL_HTTP_500")) as model:
                self.assertEqual(EVAL.run(self.args(directory, max_attempts=2)), 1)
                self.assertEqual(model.call_count, 2)
            summary = json.loads((Path(directory) / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["stop_reason"], "ATTEMPT_LIMIT")
            self.assertFalse(summary["passed"])

    def test_resume_rejects_changed_validator_or_selected_oracle(self):
        out = EVAL.ROOT / "out"
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as directory:
            root = Path(directory)
            skill = root / "skill"
            (skill / "scripts").mkdir(parents=True)
            validator_path = skill / "scripts/icd_tool.py"
            original_validator = (EVAL.SKILL / "scripts/icd_tool.py").read_bytes()
            validator_path.write_bytes(original_validator)
            shutil.copyfile(EVAL.SKILL / "SKILL.md", skill / "SKILL.md")
            fixtures = root / "fixtures"
            fixtures.mkdir()
            shutil.copyfile(EVAL.FIXTURES / "ping.h", fixtures / "ping.h")
            shutil.copyfile(EVAL.FIXTURES / "expected.json", fixtures / "expected.json")
            with patch.object(EVAL, "SKILL", skill), patch.object(EVAL, "FIXTURES", fixtures):
                args = self.args(str(root / "run"))
                with patch.object(EVAL, "request_model", return_value=(json.dumps(self.minimal_ir()), "fake")):
                    self.assertEqual(EVAL.run(args), 0)
                args.resume = True
                validator_path.write_bytes(original_validator + b"\n# Synthetic QA baseline mutation\n")
                with patch.object(EVAL, "request_model") as model:
                    with self.assertRaisesRegex(ValueError, "Resume fingerprint differs"):
                        EVAL.run(args)
                    model.assert_not_called()
                validator_path.write_bytes(original_validator)
                oracle_path = fixtures / "expected.json"
                oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
                oracle["source"]["facts"]["messages"][0]["id"] = 18
                oracle_path.write_text(json.dumps(oracle), encoding="utf-8")
                with patch.object(EVAL, "request_model") as model:
                    with self.assertRaisesRegex(ValueError, "Resume fingerprint differs"):
                        EVAL.run(args)
                    model.assert_not_called()

    def test_completed_resume_revalidates_modified_artifact(self):
        out = EVAL.ROOT / "out"
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as directory:
            args = self.args(directory)
            ir = self.minimal_ir()
            with patch.object(EVAL, "request_model", return_value=(json.dumps(ir), "fake")):
                self.assertEqual(EVAL.run(args), 0)
            ir["messages"][0]["id"] = 18
            EVAL.save_json(Path(directory) / "definition-1.json", ir)
            args.resume = True
            with patch.object(EVAL, "request_model") as model:
                self.assertEqual(EVAL.run(args), 1)
                model.assert_not_called()
            state = json.loads((Path(directory) / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stop_reason"], "RESUME_ARTIFACT_FAILED")
            self.assertFalse(state["passed"])

    def test_ambiguous_output_stops_without_repair_invitation(self):
        out = EVAL.ROOT / "out"
        out.mkdir(exist_ok=True)
        ir = self.minimal_ir()
        ir["endian"] = None
        ir["unresolved"] = ["endian is missing in source"]
        with tempfile.TemporaryDirectory(dir=out) as directory:
            with patch.object(EVAL, "request_model", return_value=(json.dumps(ir), "fake")) as model:
                self.assertEqual(EVAL.run(self.args(directory, case="ambiguity")), 0)
                self.assertEqual(model.call_count, 1)


if __name__ == "__main__":
    unittest.main()
