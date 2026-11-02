# Model and environment QA

This skill has three separate qualifications: deterministic tool behavior, API extraction behavior of the explicitly recorded model, and actual Claude Code workflow behavior. None substitutes for another. The historical production plan is `docs/plans/udpsim-icd-authoring-plan.md`; extraction provenance is recorded in `PROVENANCE.md` at this repository root.

## API extraction harness

`tests/run_udpsim_model_eval.py` uses Python 3.10+ standard library, raw synthetic fixtures, the current skill text, and a held-out fact oracle. It calls the real IR validator and feeds only validator diagnostics back to the model, at most three attempts. A valid but semantically wrong definition fails the held-out check. Missing required facts must remain unresolved, with conversion blocked. Source-fact oracle answers never enter model feedback.

This is extraction-only API QA: the harness executes validation on behalf of the model. It does not test the model's native tool calls, Claude skill discovery, tool permissions, or VS Code integration. `document-excerpt` is a text fixture, not PDF extraction evidence. The harness does not issue `TARGET_MODEL_PASS`.

Configure the complete API URL in `UDPSIM_MODEL_ENDPOINT`, and credentials only in the process environment variable `UDPSIM_MODEL_TOKEN`. The endpoint/token are not written into reports. Supported providers are `anthropic` (Bifrost-compatible Bearer authentication), `openai` (chat-completions), and `ollama`. Request and response model labels are recorded separately. Anthropic responses skip thinking blocks and read text blocks; unexpected tool-use blocks fail explicitly because no tools were offered by this extraction-only client. Streaming SSE is outside this harness.

From the repository root, with an authorized endpoint configured:

```powershell
python tests/run_udpsim_model_eval.py --provider anthropic --model qwen3.6-27b --case source --mode with-skill --work-dir out/udpsim-model/source-01
python tests/run_udpsim_model_eval.py --provider anthropic --model qwen3.6-27b --case ambiguity --mode with-skill --work-dir out/udpsim-model/ambiguity-01
python tests/run_udpsim_model_eval.py --provider anthropic --model qwen3.6-27b --case document-excerpt --mode with-skill --work-dir out/udpsim-model/document-01
```

Use a fresh work directory per session. `--resume` requires matching prompt/source/model/provider, validator bytes, selected private oracle, and hashed endpoint identity. All instructions actually included in the extraction prompt are covered; linked references that were not loaded are not claimed as tested context. A completed pass revalidates its saved artifact against the unchanged validator and oracle without making a new model call. Resume consumes the remaining attempt budget and never resets a completed failure into a pass. If a baseline changes, start a fresh run. `--mode baseline` omits the skill while retaining the same output contract, source and private evaluator, supporting a scoped A/B experiment. The maximum network timeout is 120 seconds per request. Failures and each response/validator result are persisted under ignored `out/`; actual material must not enter Git. Duplicate JSON object keys and nonfinite numbers are rejected before canonicalizing model output.

`python -m unittest discover -s tests -p test_udpsim_model_eval.py` checks the client using a fake localhost HTTP server. It covers thinking-first Anthropic replies, explicitly rejected unexpected tools, OpenAI/Ollama envelopes, HTTP 500, context-overflow-as-500, timeout, malformed content, source-fact mismatch and safe ambiguity stops. These are protocol/fault tests, not measured Qwen performance or actual Bifrost compatibility.

## Closest-environment test before offline import

Prefer the exact Qwen3.6-27B weights on an authorized cloud GPU, served through a Bifrost instance and Claude Code 2.1.312. Record model revision, quantization, inference engine, context cap, sampling defaults and gateway version. The internal server's implementation/quantization is not yet known, so a cloud setup is a reproducible approximation even when the model family matches. Downloading cloud weights or provisioning paid compute is a separate resource choice; do not substitute a smaller model silently.

The inspected development PC has 16 GiB RAM, a 2 GiB GT 1030 and an existing 7B Qwen model. That model is substantially different from the internal 27B target; local 7B inference was stopped before a response completed and is not qualification evidence. The local Claude executable reports 2.1.109, not target 2.1.312. The user requested cloud testing rather than treating 7B as the target surrogate.

## Actual Claude Code acceptance

Run these cases with the installed Claude Code 2.1.312 in a disposable copy of the synthetic fixture workspace. Use the supported project-skill entrypoint `/udpsim-icd-authoring` or plugin entrypoint `/udpsim-icd-authoring:udpsim-icd-authoring`. Verify the command appears before beginning. Preserve normal permissions; do not use permission-bypass flags to manufacture success.

1. Source fixture: supply `tests/fixtures/udpsim-model/ping.h`, request PING for a controller simulator, and choose an ignored output directory. Require actual `IR_PASS` then `XML_PASS` from the unchanged tools. Compare with the separately held oracle and payload `11 03 2A` (`Value=42`).
2. Ambiguity fixture: supply `ambiguous.h`; require a stop for absent byte order, with no accepted final XML. A guessed endian fails, even if a validator accepts it.
3. PDF fixture: use a real synthetic PDF with inventory/detail pages and out-of-range common-header definitions. Specify physical PDF page range. Confirm reference discovery and extraction; a Markdown/text substitute does not pass this case.
4. Repair: provide a source-backed definition with an incorrect declared length; require a diagnostic-driven correction, unchanged validator and successful recheck. Repeated failure must stop at three correction rounds.
5. Packet: check known bytes and an intentionally mismatching expected value. Require nonzero failure for mismatch and a field/offset diagnostic.
6. Interruption: stop after persisting one artifact and resume in a new session. Require preserved provenance and stage completion only after rerunning the relevant unchanged gate.

Repeat each behavior case in at least three fresh sessions and retain every outcome. Record exact requested/returned model identity, Claude version, model/tool timeouts, permission failures, retries, hashes of fixture/skill/UdpSim baseline, commands and exit codes. A successful small fixture does not qualify arbitrary large documents. Record context overflow and infrastructure outages as environment failures, never as passes. Shared summaries contain synthetic identifiers only; raw model I/O stays ignored.

Acceptance requires no silent guessed mandatory facts, no false completion, unchanged validator/app, positive and negative packet verdicts, and real tool evidence. Only these actual target-environment results can justify target qualification; API-only extraction or a stronger development agent remains separately labeled.
