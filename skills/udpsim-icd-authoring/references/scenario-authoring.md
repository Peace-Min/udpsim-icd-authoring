# Scenario authoring v1

Use this route when the user wants scenario XML, not another ICD definition. The target runtime
supports Periodic sends, Manual sends and Receive-triggered Responses. A general sequence of
wait/timeout/retry/branch steps is not supported. Keep the existing UdpSim app and XML format unchanged.

## Establish intent

Obtain the local UdpSim checkout, existing Config path, exact ICD key and Send message, output directory,
targets and test values. Periodic needs its period; Response needs a Receive trigger and any requested
conditions/delay. Missing required facts block completion. Do not turn unknown test values into zero.
Config supplies device addresses; this feature does not generate Config addresses.

Use a private work directory. All commands below run locally and do not open sockets. Set `$skill`
to the directory containing SKILL.md, `$app` to the UdpSim checkout and `$work` to that work directory.

## 1. Export actual Core fields

```powershell
& "$skill/scripts/Export-ScenarioContext.ps1" -UdpSimRoot $app -ConfigPath '<config>/UdpSim.config.xml' -OutputPath "$work/context.json"
python "$skill/scripts/scenario_tool.py" catalog --context "$work/context.json"
python "$skill/scripts/scenario_tool.py" fields --context "$work/context.json" --icd 'device.icd.xml' --message 'SET_CHANNELS'
```

The exporter first invokes the current app's `tools/xml/ValidateXml.ps1 -StrictConfig`, then uses
the actual Core catalog/leaves. Nested arrays and Bits use their real expanded paths. `-IcdKey`
optionally limits exported field data to one exact Config ICD key. Do not read a whole large context
into the model when the selected template/fields suffice. `fields --direction receive` describes triggers.

Context v1 records `config_path`, `icds` (key, active targets, send/receive messages), field widths,
signedness, enum items, user/automatic headers and source/tool SHA-256 fingerprints. All configured
ICDs remain fingerprinted. Changed/missing inputs yield STALE_CONTEXT. Export again on the new PC
after transfer; absolute-path context fingerprints are not portable acceptance evidence.

## 2. Create a plan template, then fill intent

```powershell
python "$skill/scripts/scenario_tool.py" template --context "$work/context.json" --kind Periodic --icd 'device.icd.xml' --message 'SET_CHANNELS' --name 'Requested trial' --output "$work/plan.json"
```

For Response add `--trigger 'REPORT_CHANNELS'`. The template has all body leaf paths with **null**
values and null targets/period. It does not guess them. Delays default explicitly to 0 and enabled
to true, matching normal app/UI defaults; change them when the user's intent differs.

Plan root has exactly `schema_version=1`, `context_sha256`, `name`, `unresolved` and `entries`.
Every entry has `kind`, `name`, `icd`, `message`, `targets`, `values`. Additional keys:

- Periodic: required `period_ms`, `start_delay_ms`; optional boolean `enabled`.
- Manual: no timing, trigger, condition or enabled attributes.
- Response: required `trigger`, `delay_ms`, `conditions`; optional boolean `enabled`.

`targets` is `"*"` or a nonempty array of exact active device names for that ICD. `values` is an
object mapping every body leaf to a **string** (enum name, decimal integer or 0x bit pattern).
Optional user-header leaf values can be added; omitted ones use runtime zero and are reported.
Automatic id/length/seq cannot be set. Conditions map Receive-trigger body paths to strings;
headers cannot be conditions. An empty conditions object means any reception of that trigger.

Keep `unresolved=[]` only when required intent is established. Root/entry unknown properties and
duplicate JSON keys are rejected. Times are JSON integers: period 10..2147483647, delays 0..2147483647.
Booleans are JSON true/false. Preserve case and literal numeric strings; positive signed decimal
must fit its signed range, while hex may specify all bits. Numeric enum bit patterns are allowed
by the app even if not named in that enum; do not add an invented enum restriction.

For multiple requested entries, combine their entry objects under one root using the same current
context hash. XML is emitted in Periodic/Manual/Response groups, keeping within-group order.
Never infer a state-machine ordering from entry order.

## 3. Generate draft and run the actual gate

```powershell
python "$skill/scripts/scenario_tool.py" generate --context "$work/context.json" --plan "$work/plan.json" --output "$work/trial.scenario.xml"
& "$skill/scripts/Test-ScenarioXml.ps1" -UdpSimRoot $app -ConfigPath '<config>/UdpSim.config.xml' -ScenarioPath "$work/trial.scenario.xml"
```

Generation checks source freshness, the bound context hash, direction, targets, paths, complete body
values, allowed headers/conditions, value widths and times. It writes UTF-8 BOM/CRLF XML atomically.
A failed generation preserves previous output; that old file is not evidence that the new request passed.
Output must not overwrite context, plan, Config, ICD or tool sources, or the Skill implementation.

`SCENARIO_DRAFT_CREATED` explicitly says Core validation NOT_RUN. `Test-ScenarioXml.ps1` invokes
the actual app checker with `-ConfigPath`, `-ScenarioPath`, `-StrictConfig`. Real exit 0 alone yields
`SCENARIO_PASS`; invalid definitions yield SCENARIO_FAIL, unavailable prerequisites BLOCKED_ENV.
Both PowerShell tools accept `-MSBuildPath` for another installed toolchain.

Core/packet/scenario gates share a build directory; run them sequentially per checkout. Do not change
validators or user intent to force a pass. Preserve intent, context, plan, XML, real command/exits,
omitted header defaults and unresolved facts. Stop after at most three source-backed correction rounds.

Core acceptance does not prove the test's operational intent or device behavior. Runtime scenario
loading/execution and actual internal Qwen/Claude Code acceptance are separate from file validation.
