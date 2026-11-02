"""Check an Anthropic-compatible gateway without claiming model/skill qualification."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_REPLY = 4 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_report_path(value: str) -> Path:
    path = Path(value).resolve()
    try:
        path.relative_to(ROOT / "out")
    except ValueError:
        raise ProbeError("REPORT_MUST_BE_UNDER_IGNORED_OUT") from None
    if path.suffix.lower() != ".json":
        raise ProbeError("REPORT_MUST_BE_JSON")
    return path


def save_report(path: Path, report: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def check_endpoint(base_url: str, live: bool):
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ProbeError("INVALID_BASE_URL")
    if parsed.query or parsed.fragment or not parsed.path.rstrip("/").endswith("/anthropic"):
        raise ProbeError("BASE_URL_MUST_END_IN_ANTHROPIC")
    if not live and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ProbeError("MOCK_REQUIRES_LOOPBACK_GATEWAY")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ProbeError("REMOTE_GATEWAY_REQUIRES_HTTPS")
    if live and os.environ.get("UDPSIM_CLOUD_FREE_QUOTA_CONFIRMED") != "1":
        raise ProbeError("CONFIRM_FREE_QUOTA_ONLY_BEFORE_LIVE")


def http_call(base_url: str, suffix: str, body, timeout: float, *, stream=False):
    headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    token = os.environ.get("UDPSIM_GATEWAY_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base_url.rstrip("/") + suffix,
                                     data=None if body is None else json.dumps(body).encode("utf-8"),
                                     headers=headers, method="GET" if body is None else "POST")
    try:
        handlers = [NoRedirect]
        if urllib.parse.urlsplit(base_url).hostname in ("127.0.0.1", "localhost", "::1"):
            handlers.append(urllib.request.ProxyHandler({}))
        with urllib.request.build_opener(*handlers).open(request, timeout=timeout) as response:
            raw = response.read(MAX_REPLY + 1)
            if len(raw) > MAX_REPLY:
                raise ProbeError("RESPONSE_TOO_LARGE")
            if stream:
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    raise ProbeError("STREAM_CONTENT_TYPE_INVALID")
                return parse_sse(raw.decode("utf-8"))
            value = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read(65536).decode("utf-8", errors="replace")
        if error.code == 500 and "maximum context length" in raw.lower():
            raise ProbeError("CONTEXT_OVERFLOW_HTTP_500") from None
        raise ProbeError("HTTP_" + str(error.code)) from None
    except (socket.timeout, TimeoutError):
        raise ProbeError("TIMEOUT") from None
    except urllib.error.URLError:
        raise ProbeError("GATEWAY_UNREACHABLE") from None
    except (UnicodeError, json.JSONDecodeError):
        raise ProbeError("INVALID_JSON_RESPONSE") from None
    if not isinstance(value, dict):
        raise ProbeError("RESPONSE_NOT_OBJECT")
    return value


def parse_sse(raw: str) -> dict:
    """Assemble indexed native tool blocks; thinking may occupy index zero."""
    blocks = {}
    partial = {}
    closed = set()
    started = False
    stopped = False
    stop_reason = None
    for frame in raw.replace("\r\n", "\n").split("\n\n"):
        lines = [line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")]
        if not lines:
            continue
        try:
            event = json.loads("\n".join(lines))
        except json.JSONDecodeError:
            raise ProbeError("SSE_INVALID_JSON") from None
        if not isinstance(event, dict):
            raise ProbeError("SSE_EVENT_NOT_OBJECT")
        kind = event.get("type")
        if kind == "error":
            raise ProbeError("SSE_ERROR_EVENT")
        if kind == "message_start":
            if started:
                raise ProbeError("SSE_DUPLICATE_MESSAGE_START")
            started = True
        elif kind == "content_block_start":
            index, block = event.get("index"), event.get("content_block")
            if not started or type(index) is not int or index < 0 or index in blocks or not isinstance(block, dict):
                raise ProbeError("SSE_INVALID_BLOCK_START")
            blocks[index] = dict(block)
            partial[index] = ""
        elif kind == "content_block_delta":
            index, delta = event.get("index"), event.get("delta")
            if type(index) is not int or index not in blocks or index in closed or not isinstance(delta, dict):
                raise ProbeError("SSE_DELTA_WITHOUT_BLOCK")
            if delta.get("type") == "input_json_delta":
                text = delta.get("partial_json")
                if blocks[index].get("type") != "tool_use" or not isinstance(text, str):
                    raise ProbeError("SSE_INVALID_TOOL_DELTA")
                partial[index] += text
            elif delta.get("type") == "text_delta":
                if not isinstance(delta.get("text"), str):
                    raise ProbeError("SSE_INVALID_TEXT_DELTA")
                blocks[index]["text"] = blocks[index].get("text", "") + delta["text"]
        elif kind == "content_block_stop":
            index = event.get("index")
            if type(index) is not int or index not in blocks or index in closed:
                raise ProbeError("SSE_STOP_WITHOUT_BLOCK")
            closed.add(index)
        elif kind == "message_delta":
            delta = event.get("delta", {})
            if not isinstance(delta, dict):
                raise ProbeError("SSE_INVALID_MESSAGE_DELTA")
            stop_reason = delta.get("stop_reason", stop_reason)
        elif kind == "message_stop":
            if not started or set(blocks) != closed:
                raise ProbeError("SSE_OPEN_OR_MISSING_BLOCKS")
            stopped = True
    if not stopped:
        raise ProbeError("SSE_TRUNCATED")
    for index, text in partial.items():
        if text:
            try:
                blocks[index]["input"] = json.loads(text)
            except json.JSONDecodeError:
                raise ProbeError("SSE_INVALID_TOOL_JSON") from None
    return {"type": "message", "content": [blocks[index] for index in sorted(blocks)], "stop_reason": stop_reason}


def text_reply(reply: dict) -> str:
    blocks = reply.get("content")
    if reply.get("type") != "message" or not isinstance(blocks, list):
        raise ProbeError("INVALID_MESSAGE_ENVELOPE")
    values = [block.get("text", "") for block in blocks
              if isinstance(block, dict) and block.get("type") == "text"]
    if not all(isinstance(value, str) for value in values):
        raise ProbeError("INVALID_TEXT_BLOCK")
    text = "".join(values)
    if not text.strip():
        raise ProbeError("NO_TEXT_REPLY")
    return text


def tool_reply(reply: dict):
    blocks = reply.get("content")
    if reply.get("type") != "message" or reply.get("stop_reason") != "tool_use" or not isinstance(blocks, list):
        raise ProbeError("NATIVE_TOOL_USE_MISSING")
    tools = [block for block in blocks if isinstance(block, dict) and block.get("type") == "tool_use"]
    if len(tools) != 1:
        raise ProbeError("EXPECTED_ONE_NATIVE_TOOL")
    block = tools[0]
    if not isinstance(block.get("id"), str) or not block["id"] or block.get("name") != "echo_probe":
        raise ProbeError("UNEXPECTED_NATIVE_TOOL")
    if block.get("input") != {"value": 7} or type(block["input"].get("value")) is not int:
        raise ProbeError("NATIVE_TOOL_ARGUMENT_MISMATCH")


def run_probe(base_url: str, model: str, timeout: float, live: bool, with_stream: bool) -> dict:
    report = {"status": "PROBE_FAIL", "profile": "live" if live else "mock", "model_requested": model,
              "qualification": "PROTOCOL_ONLY", "skill_qa": "NOT_RUN", "internal_target_qa": "NOT_RUN", "checks": []}
    try:
        check_endpoint(base_url, live)
        if not 0 < timeout <= 120:
            raise ProbeError("TIMEOUT_MUST_BE_0_TO_120_SECONDS")
        if not live and model != "udpsim-mock":
            raise ProbeError("MOCK_REQUIRES_UDPSIM_MOCK_MODEL")
        models = http_call(base_url, "/v1/models", None, timeout)
        data = models.get("data")
        if not isinstance(data, list) or not any(isinstance(item, dict) and isinstance(item.get("id"), str)
                                               and item["id"].rsplit("/", 1)[-1] == model for item in data):
            raise ProbeError("REQUESTED_MODEL_NOT_LISTED")
        report["checks"].append("models")
        base = {"model": model, "messages": [{"role": "user", "content": "Reply with QA_OK only."}]}
        count = http_call(base_url, "/v1/messages/count_tokens", base, timeout)
        if type(count.get("input_tokens")) is not int or count["input_tokens"] <= 0:
            raise ProbeError("INVALID_INPUT_TOKEN_COUNT")
        report["checks"].append("count_tokens")
        report["input_token_count"] = count["input_tokens"]
        reply = http_call(base_url, "/v1/messages", {**base, "max_tokens": 2048, "stream": False}, timeout)
        text = text_reply(reply)
        if not live and text.strip() != "QA_MOCK_OK":
            raise ProbeError("MOCK_SENTINEL_MISSING")
        report["model_returned"] = reply.get("model", "unknown")
        report["checks"].append("text_reply")
        body = {**base, "max_tokens": 2048, "stream": False,
                "messages": [{"role": "user", "content": "Call echo_probe once with value 7."}],
                "tools": [{"name": "echo_probe", "description": "Return a synthetic integer; no side effects.",
                           "input_schema": {"type": "object", "properties": {"value": {"type": "integer"}},
                                            "required": ["value"], "additionalProperties": False}}],
                "tool_choice": {"type": "tool", "name": "echo_probe"}}
        tool_reply(http_call(base_url, "/v1/messages", body, timeout))
        report["checks"].append("native_tool_use")
        if with_stream:
            tool_reply(http_call(base_url, "/v1/messages", {**body, "stream": True}, timeout, stream=True))
            report["checks"].append("streamed_native_tool_use")
        report["status"] = "CLOUD_PROTOCOL_PASS" if live else "GATEWAY_MOCK_PASS"
    except ProbeError as error:
        report["error"] = str(error)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:18080/anthropic")
    parser.add_argument("--model", required=True)
    parser.add_argument("--report", default="out/cloud-qa/probe.json")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = safe_report_path(args.report)
        started = time.monotonic()
        report = run_probe(args.base_url, args.model, args.timeout, args.live, args.stream)
        report["seconds"] = round(time.monotonic() - started, 3)
        save_report(path, report)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] in ("GATEWAY_MOCK_PASS", "CLOUD_PROTOCOL_PASS") else 1
    except (ProbeError, OSError) as error:
        print(json.dumps({"status": "PROBE_INPUT_OR_IO_FAIL", "error": str(error)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
