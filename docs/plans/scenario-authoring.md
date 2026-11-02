# Scenario authoring support

Implement only in this standalone Skill repository. Preserve the UdpSim app/XML contract.

1. Export a versioned scenario context from the actual Core's Config/ICD catalog and expanded leaves
   after strict Config/ICD validation. Include exact ICD keys, active targets, writable user headers,
   automatic headers, Send/Receive codes, field widths/enums and input/tool source hashes.
2. Add a standard-library Python tool for a null-valued JSON plan template and deterministic XML
   drafts. Support only Periodic, Manual and Response. Require all body values; forbid automatic
   headers, invalid paths/directions, stale contexts and guessed missing inputs. Keep numeric strings.
3. Add an actual Config+Scenario Core gate using the existing app tool with -StrictConfig. Only
   its real zero exit qualifies SCENARIO_PASS. Generation alone is SCENARIO_DRAFT_CREATED.
4. Test nested arrays/Bits/enums, optional header omission, multi-ICD/target identity, three entry
   kinds, missing values, wrong directions/paths/types/ranges, stale sources and failed environments.
   Use independent synthetic fixtures and actual Core positive/negative checks; no live sockets.
5. Update lean Skill routing, entrypoints, references, Wiki/sequence documentation, packaging and
   synchronized 0.2.0 metadata. Preserve historical QA as historical. Run relevant regression gates.

No Config address generation, device operation, general state-machine execution, packet format
extension, external model calls or mutation of UdpSim's validators is part of this change.

Completed 2026-11-02: all five steps implemented. Full regression passed (218 Python tests,
24 scenario integration checks), plus independent Codex authoring and parent intent comparison.
Internal target-model and real-device acceptance remain NOT_RUN. See the scenario Wiki and
PROVENANCE for measured scope; local raw evidence is excluded from Git.
