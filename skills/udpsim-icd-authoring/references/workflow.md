# Intermediate definition and evidence workflow

## Private work record

Use the user's work directory for source inventory, per-message IR, conversion output, validation logs and the completion record. Capture source and tool identities, current UdpSim commit, requested scope, simulator role, completed/blocked message IDs, latest round, gate exit codes and next action. Save after every round so a new session can resume. A log is sensitive source-derived material even when it contains only field names.

On resume, inspect the current IR/XML and input identity. A previous pass is stale if input or tool baseline changed. Resume the first incomplete message; do not regenerate completed messages without a reason.

## IR v1

The bundled validator defines the executable contract. Use its complete synthetic example rather than inventing attributes. Unknown attributes are rejected. The common representation is independent of whether its evidence came from a PDF or source.

Root keys:

- `schema_version`: integer `1`.
- `name`: nonempty ICD name; `endian`: explicit `big` or `little`.
- `evidence`: nonempty list of `{ "source": "source label", "locator": "physical PDF p.8 / file:line / global rule" }`.
- `unresolved`: list of unresolved requirements. Any unresolved required fact blocks conversion; do not erase it without new evidence.
- `enums`: list of `{name,items:[{name,value}]}`.
- `types`: list of `{name,fields:[...]}` for reusable structs.
- `header`: ordered field list.
- `messages`: list of `{direction,code,id,name,length,fields}`; `direction` is `send` or `receive`, relative to the simulator, and `length` includes the header.

Fields have `name,type`; optional supported keys are `count,enum,bits,role,max,scope,response`. Bits use `{name,from,to,enum?}`. All scalar numeric values are JSON integers. Do not write JSON booleans where integers are expected. Omit `count` for a scalar; a count of `1` is an array and creates an indexed path.

Messages, fields and Bits may also carry optional `evidence` lists in the same `{source,locator}` form. Prefer these for direct per-fact tracing rather than adding arbitrary schema keys. A simulator role belongs in the task/work record; do not invent a `simulator_role` root property.

Header fields are primitive integers only, with exactly one `role=id`, exactly one `role=length`, at most one `role=seq`; roleless fields are manual header values. Header arrays, structs, enums and Bits are not supported. `max`, `scope`, `response` belong only to seq. Body/struct fields cannot carry header-role attributes. Structs cannot have enum/Bits; Bits are integer fields' children. Recursive types are invalid.

IR evidence is a trace index, not an automatic proof that the stated source says the right thing. Keep a private per-fact mapping when multiple pages/files provide the definition. Record simulator role/direction basis in the work record even if not a root schema key.

## Validation and bounded correction

Set `$skill` to the skill directory. First validate IR, then convert, then invoke the Core bridge with the explicit UdpSim checkout:

```powershell
python "$skill/scripts/icd_tool.py" validate --input '<work>/definition.json'
python "$skill/scripts/icd_tool.py" convert --input '<work>/definition.json' --output '<work>/device.icd.xml'
& "$skill/scripts/Test-IcdXml.ps1" -UdpSimRoot '<UdpSim>' -IcdPath '<work>/device.icd.xml'
```

The bridge's final XML gate uses the actual repository tool:

```powershell
& '<UdpSim>/tools/xml/ValidateXml.ps1' -IcdPath '<output>/device.icd.xml' -ListFields
```

For optional Config/scenario files, the integration gate is:

```powershell
& '<UdpSim>/tools/xml/ValidateXml.ps1' -ConfigPath '<output>/UdpSim.config.xml' -ScenarioPath '<output>/demo.scenario.xml' -StrictConfig
```

Run the repository wrapper from the expected working directory; quote paths and use the existing native shell. An alternate MSBuild installation can be supplied using the repository tool's `-MSBuildPath`. Do not execute simultaneous Core builds in the same checkout. Missing or failing toolchains yield an environment failure, never an XML pass.

Classify diagnostic feedback:

1. Data error supported by current source, such as wrong count transcription or malformed path: fix the IR and regenerate, then rerun both gates.
2. Missing/conflicting source fact or unsupported feature: leave blocked with exact source references; ask for the fact or authoritative version.
3. Environment failure, such as missing Python, MSBuild, file or extractor: name the missing component and preserve work; do not change packet definitions.
4. Packet mismatch: compare source, IR, generated XML, capture identity and expected values. A capture is evidence to investigate, not a blanket instruction to rewrite the definition.

Use at most three correction rounds per message. A timeout consumes no semantic conclusion: record it and preserve files. On repeated infrastructure failure, stop rather than silently retrying forever or rerunning hardware operations.

## Payload check

The supplied observation must contain exactly the UDP application payload, without Ethernet/IP/UDP headers. The checker accepts raw binary or a hex payload file; export that payload from PCAP/PCAPNG in a capture tool before running this checker. It neither captures live traffic nor operates the remote device.

```powershell
& "$skill/scripts/Test-UdpPayload.ps1" -UdpSimRoot '<UdpSim>' -IcdPath '<work>/device.icd.xml' -PayloadPath '<work>/payload.hex' -Format hex -Message 'MESSAGE_CODE' -ReportPath '<work>/packet-report.json'
```

Use `-Format binary` for raw bytes. Supply `-ExpectedPath '<work>/expected.json'` when independent expected values are available. Read [packet-validation.md](packet-validation.md) for exact semantics. The expected file is an object mapping editable leaf paths to strings, for example:

```json
{"Source":"7","Channels[0].Reading":"-5","Channels[0].Flags.Ready":"On"}
```

Numeric JSON values are not accepted in this expected-value file; it deliberately uses the Core scenario value syntax, unlike integer-only IR numeric scalars. Automatic ID/length headers are checked from the packet definition. Sequence expectation uses the separate `-ExpectedSeq` option. Include the actual output/exit in the completion record. Do not assume a successful structural decode compared every field to an expected value.

## Completion levels

- `IR_PASS`: the intermediate validator accepted the implemented syntax and consistency constraints.
- `XML_PASS`: the actual UdpSim XML validation command exited zero for these current files.
- `PACKET_DECODE_PASS`: observed ID/length/structure decoded; no independent field-value expectations were checked.
- `PACKET_EXPECTED_SUBSET_MATCH`: all supplied expected leaves matched, but at least one editable body/manual-header leaf was not expected.
- `PACKET_EXPECTED_MATCH`: all editable body/manual-header leaves were explicitly expected and matched. Sequence is compared only when `-ExpectedSeq` is supplied; unspecified Bits are not checked.
- `PACKET_FAIL`: packet comparison or input validation failed; preserve the diagnostic and nonzero exit.
- `SAME_MODEL_PROXY_PASS`: synthetic behavior cases passed using the identified actual Qwen 27B provider, local Bifrost and Claude Code 2.1.312. Verify and record weights/version/config where possible; requested/returned name agreement alone is not proof of identical weights. This does not establish internal gateway acceptance.
- `TARGET_MODEL_PASS`: acceptance actually ran through the internal backend/gateway and intended Claude Code version, with retained evidence. A different agent, 7B substitute, cloud proxy or API-only smoke test does not establish this.
- `NOT_RUN` or `BLOCKED_ENV`: the check was not performed or could not run; give the reason.

None of these levels implies another. Structural packet acceptance cannot establish correct endian for arbitrary bytes without an independent expected value. Shared encoder/decoder round trips may share the same mistake. A real independently known packet is stronger evidence. None of these checks proves the remote device performed its intended operation.

The final handover contains output paths, input/tool baseline, exact gates run and exits, remaining blocked messages or facts, packet-check scope, target-model qualification status, and the next action. Never claim completion based only on a JSON/schema pass or on the app codec silently filling missing values.
