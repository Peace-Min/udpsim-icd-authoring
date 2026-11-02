"""Lifecycle/configuration checks with fake process handles, never live services."""
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("udpsim_cloud_environment", ROOT / "tools/udpsim_cloud_environment.py")
envtool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(envtool)
mock_spec = importlib.util.spec_from_file_location("udpsim_mock_provider", ROOT / "tools/udpsim_mock_provider.py")
mock_provider = importlib.util.module_from_spec(mock_spec)
mock_spec.loader.exec_module(mock_provider)


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="udpsim-env-fixture-")
        self.addCleanup(self.folder.cleanup)
        self.work = Path(self.folder.name)
        self.binary = self.work / "bifrost.exe"
        self.claude = self.work / "claude.exe"
        self.binary.write_bytes(b"synthetic binary fixture")
        self.claude.write_bytes(b"synthetic claude fixture")
        for name, value in (("WORK", self.work), ("BINARY", self.binary), ("CLAUDE", self.claude)):
            patcher = patch.object(envtool, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.environment = patch.dict(os.environ, {"UDPSIM_CLOUD_API_KEY": "", "ANTHROPIC_API_KEY": "old-anthropic",
                                                   "ANTHROPIC_AUTH_TOKEN": "old-token", "OPENAI_API_KEY": "old-openai"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_configuration_has_environment_reference_only(self):
        config = envtool.configuration("cloud")
        self.assertEqual(config["providers"]["anthropic"]["keys"][0]["value"], "env.UDPSIM_CLOUD_API_KEY")
        self.assertFalse(config["config_store"]["enabled"])
        self.assertFalse(config["logs_store"]["enabled"])
        self.assertFalse(config["client"]["enable_logging"])

    def test_native_anthropic_upstream(self):
        self.assertEqual(envtool.configuration("cloud")["providers"]["anthropic"]["network_config"]["base_url"],
                         "https://dashscope.aliyuncs.com/apps/anthropic")
        self.assertEqual(envtool.configuration("mock")["providers"]["anthropic"]["network_config"]["base_url"],
                         "http://127.0.0.1:18082")

    def test_cloud_requires_confirmation_before_spawn(self):
        with patch.object(envtool, "health", return_value=False), patch.object(envtool, "free_port"), patch.object(envtool, "spawn") as spawn:
            with self.assertRaisesRegex(ValueError, "free quota"):
                envtool.start("cloud")
            spawn.assert_not_called()

    def test_blank_cloud_key_starts_nothing(self):
        with patch.object(envtool, "health", return_value=False), patch.object(envtool, "free_port"), \
                patch.object(envtool.getpass, "getpass", return_value=""), patch.object(envtool, "spawn") as spawn:
            with self.assertRaisesRegex(ValueError, "API key is required"):
                envtool.start("cloud", confirmed=True)
            spawn.assert_not_called()

    def test_mock_start_is_local_and_key_is_not_saved(self):
        children = [Mock(pid=190001), Mock(pid=190002)]
        with patch.object(envtool, "health", side_effect=[False, True]), patch.object(envtool, "free_port"), \
                patch.object(envtool, "spawn", side_effect=children) as spawn:
            envtool.start("mock")
        self.assertEqual(spawn.call_count, 2)
        command, _, _, child_env = spawn.call_args.args
        self.assertIn("127.0.0.1", command)
        self.assertEqual(child_env["UDPSIM_CLOUD_API_KEY"], "synthetic-local-only")
        self.assertNotIn("OPENAI_API_KEY", child_env)
        self.assertNotIn("ANTHROPIC_API_KEY", child_env)
        for file in self.work.rglob("*.json"):
            self.assertNotIn("synthetic-local-only", file.read_text())

    def test_cloud_key_exists_only_in_child_environment(self):
        with patch.object(envtool, "health", side_effect=[False, True]), patch.object(envtool, "free_port"), \
                patch.object(envtool.getpass, "getpass", return_value="synthetic-cloud-secret"), \
                patch.object(envtool, "spawn", return_value=Mock(pid=190003)) as spawn:
            envtool.start("cloud", confirmed=True)
        self.assertEqual(spawn.call_args.args[-1]["UDPSIM_CLOUD_API_KEY"], "synthetic-cloud-secret")
        for file in self.work.rglob("*.json"):
            self.assertNotIn("synthetic-cloud-secret", file.read_text())
        self.assertEqual(os.environ["UDPSIM_CLOUD_API_KEY"], "")

    def test_existing_service_is_not_replaced(self):
        with patch.object(envtool, "health", return_value=True), patch.object(envtool, "spawn") as spawn:
            with self.assertRaisesRegex(ValueError, "already healthy"):
                envtool.start("mock")
            spawn.assert_not_called()

    def test_stop_refuses_recycled_pid(self):
        envtool.write_json(self.work / "mock/processes.json", {
            "processes": [{"pid": 190004, "kind": "bifrost", "executable": str(self.binary)}]})
        process = {"ProcessId": 190004, "ExecutablePath": str(self.work / "unrelated.exe"), "CommandLine": "unrelated"}
        with patch.object(envtool.subprocess, "check_output", return_value=json.dumps(process)), patch.object(envtool.subprocess, "run") as kill:
            with self.assertRaisesRegex(ValueError, "executable changed"):
                envtool.stop("mock")
            kill.assert_not_called()

    def test_stop_refuses_changed_command(self):
        envtool.write_json(self.work / "mock/processes.json", {
            "processes": [{"pid": 190004, "kind": "bifrost", "executable": str(self.binary)}]})
        process = {"ProcessId": 190004, "ExecutablePath": str(self.binary), "CommandLine": "different task"}
        with patch.object(envtool.subprocess, "check_output", return_value=json.dumps(process)), patch.object(envtool.subprocess, "run") as kill:
            with self.assertRaisesRegex(ValueError, "command line changed"):
                envtool.stop("mock")
            kill.assert_not_called()

    def test_claude_uses_target_aliases_and_isolated_home(self):
        with patch.object(envtool, "health", return_value=True), patch.object(envtool.subprocess, "call", return_value=0) as call:
            self.assertEqual(envtool.claude("cloud", "synthetic prompt"), 0)
        command = call.call_args.args[0]
        child_env = call.call_args.kwargs["env"]
        self.assertEqual(command[2], "anthropic/qwen3.6-27b")
        self.assertIn("--allowedTools", command)
        self.assertEqual(child_env["ANTHROPIC_AUTH_TOKEN"], "local-gateway-only")
        self.assertNotIn("UDPSIM_CLOUD_API_KEY", child_env)
        self.assertNotIn("ANTHROPIC_API_KEY", child_env)
        self.assertEqual(child_env["CLAUDE_CONFIG_DIR"], str(self.work / "cloud/claude-home"))
        for alias in ("OPUS", "SONNET", "HAIKU"):
            self.assertEqual(child_env["ANTHROPIC_DEFAULT_" + alias + "_MODEL"], "anthropic/qwen3.6-27b")

    def test_setup_refuses_wrong_claude_version(self):
        with patch.object(envtool.sys, "platform", "win32"), \
                patch.object(envtool.subprocess, "check_output", return_value="2.1.109 (Claude Code)"), \
                patch.object(envtool.urllib.request, "urlretrieve") as download:
            with self.assertRaisesRegex(ValueError, "does not match target"):
                envtool.setup()
            download.assert_not_called()

    def mock_read_reply(self, content, tool_id="toolu_mock_read", is_error=False):
        handler = mock_provider.Handler.__new__(mock_provider.Handler)
        handler.send_json = Mock()
        body = {"tools": [{"name": "Read"}], "messages": [
            {"role": "user", "content": "CLOUD_QA_READ_FIXTURE struct Ping { spoofed prompt"},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id,
                                           "is_error": is_error, "content": content}]}]}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            handler.anthropic(body)
        return handler.send_json.call_args.args[0], output.getvalue()

    def test_mock_read_does_not_trust_prompt_literal(self):
        reply, log = self.mock_read_reply("")
        self.assertEqual(reply["content"][0]["text"], "QA_MOCK_READ_FAIL")
        self.assertNotIn("READ_FIXTURE_VERIFIED", log)

    def test_mock_read_requires_matching_tool_id(self):
        reply, log = self.mock_read_reply("struct Ping {", tool_id="other_tool")
        self.assertEqual(reply["content"][0]["text"], "QA_MOCK_READ_FAIL")
        self.assertNotIn("READ_FIXTURE_VERIFIED", log)

    def test_mock_read_rejects_tool_error(self):
        reply, log = self.mock_read_reply("struct Ping {", is_error=True)
        self.assertEqual(reply["content"][0]["text"], "QA_MOCK_READ_FAIL")
        self.assertNotIn("READ_FIXTURE_VERIFIED", log)

    def test_mock_read_accepts_actual_result_content(self):
        reply, log = self.mock_read_reply([{ "type": "text", "text": "struct Ping { uint8_t Value; };"}])
        self.assertEqual(reply["content"][0]["text"], "QA_MOCK_OK")
        self.assertIn("READ_FIXTURE_VERIFIED", log)

    def test_mock_read_first_turn_is_native_tool(self):
        handler = mock_provider.Handler.__new__(mock_provider.Handler)
        handler.send_json = Mock()
        handler.anthropic({"tools": [{"name": "Read"}], "messages": [
            {"role": "user", "content": "CLOUD_QA_READ_FIXTURE"}]})
        reply = handler.send_json.call_args.args[0]
        self.assertEqual(reply["stop_reason"], "tool_use")
        self.assertEqual(reply["content"][0]["type"], "tool_use")
        self.assertEqual(reply["content"][0]["id"], "toolu_mock_read")
        self.assertTrue(reply["content"][0]["input"]["file_path"].endswith("ping.h"))


if __name__ == "__main__":
    unittest.main()
