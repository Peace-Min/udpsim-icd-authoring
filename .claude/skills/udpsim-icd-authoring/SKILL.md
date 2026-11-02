---
name: udpsim-icd-authoring
description: Clone-time entrypoint for UdpSim ICD authoring, source-bound Periodic/Manual/Response scenario drafts and actual validation, with optional raw UDP payload checks.
---

# UdpSim ICD Authoring Entrypoint

Read and follow `skills/udpsim-icd-authoring/SKILL.md` before acting. Resolve scripts and
references from that canonical skill directory.

Treat arguments as the source path and message/page scope, simulator role, local UdpSim
checkout path, and private output directory. If a required fact is absent, ask only for the
missing fact. Do not infer packet direction from an external equipment's viewpoint.

Use `scripts/icd_tool.py` for intermediate validation and XML generation,
`scripts/Test-IcdXml.ps1` for the actual UdpSim validation gate, and
`scripts/Test-UdpPayload.ps1` only when observed UDP payload bytes are supplied.
For scenario requests follow the canonical scenario-authoring reference and use the Core context
exporter, scenario plan generator and `Test-ScenarioXml.ps1` strict integration gate.
Do not modify source specifications, the simulator, schemas, or validators to make an
artifact pass. Record unresolved facts rather than guessing them.
