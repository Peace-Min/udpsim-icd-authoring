# Extraction and QA provenance

Extracted from [Peace-Min/peace-skillbank](https://github.com/Peace-Min/peace-skillbank)
at commit [fe485f2a113221a6ba574dfaa939ac7af6fad381](https://github.com/Peace-Min/peace-skillbank/commit/fe485f2a113221a6ba574dfaa939ac7af6fad381).
Copyright and MIT licensing are retained. Original skill-bank registration remains available.

This repository contains only udpsim-icd-authoring, its entrypoints, related tools, synthetic fixtures
and documentation. It contains no other bank Skills, UdpSim app code, installed model/runtime,
private input or raw model I/O. UdpSim remains an external checkout.

Standalone metadata starts at 0.1.0. Plugin namespace is now
`/udpsim-icd-authoring:udpsim-icd-authoring`; clone-time `/udpsim-icd-authoring` is retained.
Transfer-package paths and current usage instructions are adapted. The canonical runtime Skill
and four converter/Core/payload implementation files retain their upstream bytes.

The dated Wiki QA outcomes (including the 189-test run and eight Codex actor cases) are historical
evidence from the source repository. Raw ignored out/ logs and completed actor workspaces were not
copied. Moving a repository does not establish new model qualification or portable checkpoint validity.
Standalone regression results are recorded below after execution; no external models are called
during extraction. Internal Qwen/Claude Code acceptance remains NOT_RUN.

## Standalone validation

- Python regression: **193 passed** (189 inherited checks plus 4 standalone layout checks), no external model calls.
- Actual UdpSim Core/payload regression: **25 checks passed** through `tests/validate.ps1 -UdpSimRoot ...`.
- Additional synthetic stdio MCP/checkpoint suite: **8 tool cases passed**, including 4 payload positive/negative pairs.
- Skill validator, standalone plugin/marketplace manifests and local document links passed.
- Canonical SKILL.md and the four runtime implementation files match the upstream bytes exactly.
- Transfer package: format-2 manifest and SHA-256 for **162 files** verified. The extracted standalone
  layout passed its four checks; relocated converter/Core and two payload positive/negative pairs passed.
  A PowerShell 5.1 default-parameter path issue was corrected during this test.
- No new model-quality run or internal Qwen/Claude Code acceptance is implied by extraction.
