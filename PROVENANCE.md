# Extraction and QA provenance

Extracted from [Peace-Min/peace-skillbank](https://github.com/Peace-Min/peace-skillbank)
at commit [fe485f2a113221a6ba574dfaa939ac7af6fad381](https://github.com/Peace-Min/peace-skillbank/commit/fe485f2a113221a6ba574dfaa939ac7af6fad381).
Copyright and MIT licensing are retained. Original skill-bank registration remains available.

This repository contains only udpsim-icd-authoring, its entrypoints, related tools, synthetic fixtures
and documentation. It contains no other bank Skills, UdpSim app code, installed model/runtime,
private input or raw model I/O. UdpSim remains an external checkout.

Standalone metadata starts at 0.1.0. Plugin namespace is now
`/udpsim-icd-authoring:udpsim-icd-authoring`; clone-time `/udpsim-icd-authoring` is retained.
Transfer-package paths and current usage instructions were adapted. At extraction, the canonical
runtime Skill and four converter/Core/payload files matched upstream bytes. Version 0.2.0 extends
the Skill's scenario routing and adds context/template/generation/strict scenario-gate tools.
The four original converter/Core/payload implementation files remain unchanged.

The dated Wiki QA outcomes (including the 189-test run and eight Codex actor cases) are historical
evidence from the source repository. Raw ignored out/ logs and completed actor workspaces were not
copied. Moving a repository does not establish new model qualification or portable checkpoint validity.
Standalone regression results are recorded below after execution; no external models are called
during extraction. Internal Qwen/Claude Code acceptance remains NOT_RUN.

## Standalone extraction validation (0.1.0)

- Python regression: **193 passed** (189 inherited checks plus 4 standalone layout checks), no external model calls.
- Actual UdpSim Core/payload regression: **25 checks passed** through `tests/validate.ps1 -UdpSimRoot ...`.
- Additional synthetic stdio MCP/checkpoint suite: **8 tool cases passed**, including 4 payload positive/negative pairs.
- Skill validator, standalone plugin/marketplace manifests and local document links passed.
- Canonical SKILL.md and the four runtime implementation files match the upstream bytes exactly.
- Transfer package: format-2 manifest and SHA-256 for **162 files** verified. The extracted standalone
  layout passed its four checks; relocated converter/Core and two payload positive/negative pairs passed.
  A PowerShell 5.1 default-parameter path issue was corrected during this test.
- No new model-quality run or internal Qwen/Claude Code acceptance is implied by extraction.

## Scenario authoring validation (0.2.0, 2026-11-02)

- Python regression: **218 passed**, including **25 scenario unit tests**.
- `tests/validate.ps1` passed, including existing actual Core/payload checks and **24 scenario
  integration checks** against the unchanged UdpSim checkout. The scenario checks cover all three
  kinds together, exact ICD scope, rejection cases, missing tooling and stale source/plan refusal.
- Independent Codex actor: one request produced Periodic, Manual and Response entries using the
  Skill and synthetic Config/ICDs. Parent comparison verified the requested values, targets,
  timing, condition and omitted header defaults; the real strict Core gate passed. After a helper
  edit, stale-context refusal was observed, then context refresh and strict validation passed again.
- Read-only implementation review found no blocking issue. This is Codex behavioral evidence,
  not a free-model, internal Qwen/Claude Code or real-device acceptance result.
- Transfer package: **176 file hashes verified** after extraction to a different directory;
  all **24 scenario integration checks passed** against the packaged UdpSim Core/tool sources.
- Raw local evidence stays in ignored `out/`; no private input or model I/O is published.
