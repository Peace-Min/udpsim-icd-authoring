# OpenCode Skill QA plan

Date: 2026-10-30. This plan covers actual free-model proxy QA, not internal Qwen qualification.

Execution complete: 36 units / 40 model calls; rejudged the same responses after correcting evaluator
false negatives, with no new inference. Final 18 PASS, 3 content/response failures, 15 infrastructure
failures. See [verified results and limits](../wiki/udpsim-opencode-skill-qa.md). Internal acceptance remains NOT_RUN.

## Scope and evidence boundary

Run the current `udpsim-icd-authoring` Skill through the official local OpenCode session API.
Use `flint-40b-free`, `nemotron-3.5-lightning-free`, and `glm-5.3-flash-free` where currently available.
Record requested/returned model, session, hashes, complete outcomes, retries and infrastructure failures.
Do not replace a failed free model with a paid model or silently report a different model.

The source fixtures are newly written synthetic protocols. They differ from the existing PING examples.
Only the raw input and relevant Skill/contract go to the model. `cases.json`, expected bytes/values,
and the correct intermediate definitions stay evaluator-side, outside the model workspace.
The repair case deliberately supplies a faulty seed definition; the corrected oracle is not supplied.

## Cases

1. Source-to-IR: C declarations plus explicit serialization facts. Shared 5-byte header, nested
   fixed array, signed fields, Bits/enum, big endian, and device-transmit mapped to simulator Receive.
2. Actual three-page selectable-text PDF: requested pages 2-3 reference a shared header/enum on
   page 1. Little endian and simulator Send. Parent-side pypdf extraction supplies page markers;
   this is not scanned PDF OCR or native model vision qualification.
3. Missing byte order: preserve the missing mandatory fact, do not guess, reject completion and XML.
4. Repair: supplied source-backed definition has an incorrect declared length. The real validator
   must reject it; the model corrects the definition from source, with no validator/app edits.

For accepted positive definitions, run actual IR validation and deterministic conversion, then
the real UdpSim Core authoring validator. Compare declared facts with the private oracle.
Use independently hand-calculated bytes to check payload decode and expected leaf values.
At least one changed expected leaf must produce packet mismatch, not a false pass.

## Execution limits

Prefer three fresh repetitions of each case/model. Each case permits at most three diagnostic-driven
repair attempts, with a per-request timeout no greater than 180 seconds. A missing/conflicting source
fact is a stop condition, not an invitation to clear `unresolved`. Environment failures are separate
from semantic failures. Only actual successful artifacts count; an API connection smoke is not Skill QA.

Core validators share a build output directory, so run Core/packet invocations sequentially per checkout.
Model I/O and raw reports remain in ignored `out/`. Shared Wiki records synthetic aggregates and limits.

## Ownership

- Fixture author owns `tests/fixtures/udpsim-opencode-qa/` and this plan.
- Parent owns the API evaluation harness, actual model runs and Core execution.
- Independent review checks output facts against the withheld oracle after generation.

Workers share the workspace and preserve each other's changes. No internal specifications or credentials
are introduced. `TARGET_MODEL_PASS` remains NOT_RUN until the actual internal environment is tested.
