# UdpSim priority QA strengthening

Date: 2026-10-30. Preserve the completed 36-unit baseline and its raw evidence.

Implementation/tool QA complete. Eight new fixtures, restricted native MCP adapter/runner,
actual Core/payload and process-restart checks passed. One native GLM attempt reached the free
limit before any model tool call. OpenCode native model quality remains NOT_RUN; see verified Wiki.

2026-11-02 follow-up: free OpenCode still reached its usage limit. Five fresh Codex actor contexts
used the restricted CLI/stdio MCP interface instead, with no evaluator answers provided. All eight
cases passed independent post-judgment (3 XML artifacts, 4 payload positive/negative pairs); actual
Core tool calls and fresh-context checkpoint continuation were observed. This qualifies the tested
Codex functional workflow only, not OpenCode free-model or internal Qwen acceptance.

## Work and acceptance

1. Add a separate eight-case synthetic suite, bringing the available scenarios from four to twelve:
   actual multi-message table PDF; endian authority conflict; absent shared header; variable frame;
   unknown compiler layout; conflicting document revisions; instruction-like source comments;
   repair plus checkpoint interruption/resume. Keep evaluator answers outside model-visible files.
2. Validate positive oracle IR/XML and independently calculated payloads through the actual Core.
   Blocked fixtures have no accepted XML. Expand evaluator support for multiple packet checks.
3. Add a local stdio MCP adapter exposing only source/Skill reads, candidate save, real validation,
   conversion and checkpoint operations. The model receives no shell, generic filesystem access,
   validator-edit capability or evaluator oracle. Log every actual tool call and process exit.
4. Add an isolated OpenCode native-agent runner. The model must load Skill/source and call tools;
   no parent-written candidate may masquerade as autonomous extraction. Interrupt after a real
   IR_PASS checkpoint, then use a fresh session to continue from verified files. Parent judges
   source correctness and packet expectations after tool execution.
5. Test MCP framing, failure/correction, persistence, changed-input invalidation, false completion
   rejection, and actual Core execution offline. These are tool/protocol tests, not model passes.
6. Attempt one bounded free-model native run only after transport/tool gates pass. On free limit,
   stop without paid fallback and record model QA as BLOCKED_FREE_LIMIT/NOT_RUN. Do not infer
   quota availability from an idle server. Preserve any incomplete tool evidence honestly.
7. Update Wiki with measured counts, actual model/tool boundary, remaining internal acceptance,
   and exact rerun commands. Do not publish or modify UdpSim app/validators.

## Evidence

Raw prompts, messages, tool calls and generated output stay under ignored out/. Core invocations
against the same checkout are serialized. PDF text extraction is not OCR/vision qualification.
Source-backed mismatch tests retain a withheld oracle; the adapter itself cannot establish truth.
