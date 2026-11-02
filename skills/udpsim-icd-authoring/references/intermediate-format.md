# Intermediate definition v1

Use Python **3.10 or newer**, standard library only. Provision its offline Windows installer before air-gap transfer if Python is absent; no pip packages are needed. Invoke from the native shell, using the actual Python executable if `python` is not on PATH. No model service is needed by these scripts.

The converter follows UdpSim's contract at baseline `26ec9582a4e27c5702258231fb6ac9d6c2499fe3`: `docs/wiki/file-formats.md`, `icd-structure.md`, and `tools/xml/README.md`. Read the selected local checkout's current documents before authoring. Generated XML is not complete until that checkout's actual Core validator passes.

## Required root

Every root property below is mandatory; use empty arrays where appropriate. Unknown properties are rejected at every object level. Property names are case-sensitive. Numeric attributes are **JSON integers**, not strings, floats or booleans; convert a source ID such as `0x11` to JSON `17`.

```json
{
  "schema_version": 1,
  "name": "Synthetic ping",
  "endian": "little",
  "evidence": [{"source": "synthetic-spec.txt", "locator": "section 1; simulator is controller"}],
  "unresolved": [],
  "enums": [],
  "types": [],
  "header": [
    {"name": "Id", "type": "uint8", "role": "id"},
    {"name": "Length", "type": "uint8", "role": "length"}
  ],
  "messages": [
    {"direction": "send", "code": "PING", "id": 17, "name": "Ping", "length": 3,
     "fields": [{"name": "Value", "type": "uint8"}]}
  ]
}
```

`endian` is explicitly `big` or `little`. Directions `send`/`receive` are relative to the simulator, never automatically copied from the external device's viewpoint. Store the simulator-role explanation in task/checkpoint evidence; `simulator_role` is not an IR property.

`evidence` must contain at least one `{source,locator}` with nonempty strings. `locator` records physical PDF page/section or source file lines and serialization site. The same optional `evidence` list may be attached to messages, fields and Bits. Cite evidence for packet facts during source extraction; the validator checks presence/shape, not the truth or accessibility of those citations. Keep source facts outside this public repository.

`unresolved` must be empty to pass. Preserve missing or conflicting facts there rather than inventing values; a nonempty list returns `unresolved_facts` with `action=clarify`. Other JSON errors return `correct_from_source`, which is a repair hint, not authorization to guess unavailable information.

## Groups and fields

- `enums`: `[{name,items:[{name,value}]}]`. Enum values are nonnegative bit patterns `0..4294967295`, including negative signed values represented as their bit pattern. Enum/type names and enum item names must be unique in their own scope; references must fit the field or Bits width.
- `types`: `[{name,fields:[...]}]`, at least one field per struct. Names cannot shadow primitive types. Forward references work; cycles, excessive depth and oversized expansions fail.
- `header`: ordered primitive fields. Required `{name,type}`; optional `role,max,scope,response,evidence`. No count, enum, Bits or struct. Exactly one `id` and `length` role, at most one `seq`. Only seq accepts `max` (within its unsigned bit capacity), `scope=link|message`, `response=count|echo`.
- `messages`: ordered `{direction,code,id,name,length,fields,evidence?}`. At least one message. Code and ID are separately unique across both directions. Length includes the shared header; ID and length must fit their designated header widths.
- Body/struct fields: `{name,type,count?,enum?,bits?,evidence?}`. The six primitive types are `uint8,uint16,uint32,int8,int16,int32`; otherwise type names must refer to a declared struct. Count is `1..65507`; specifying 1 still creates `[0]`. Struct fields cannot carry enum/Bits. Reserved/padding bytes must be explicit fields.
- Bits: `{name,from,to,enum?,evidence?}`, nonempty list when present; inclusive LSB-zero range within the primitive width. Names and ranges cannot overlap within a field. Put enum references on Bits, not simultaneously on the parent field.

Field, struct, enum-reference and Bits identifiers cannot contain `.`, `[` or `]`, or surrounding whitespace. Text must be XML-compatible. Overall frame and expanded primitive count are capped at 65,507, with expanded depth at most 32. The validator computes aggregate sizes without allocating every array element. UdpSim Core remains the final authority for its full loader semantics.

## Commands and output

```powershell
python <skill-dir>/scripts/icd_tool.py validate --input <work-dir>/message.json
python <skill-dir>/scripts/icd_tool.py convert --input <work-dir>/message.json --output <work-dir>/message.icd.xml
& <skill-dir>/scripts/Test-IcdXml.ps1 -UdpSimRoot <UdpSim-checkout> -IcdPath <work-dir>/message.icd.xml
```

The Python CLI emits one JSON object. Exit 0 means `status=IR_PASS`, with `xml_generated` and `xml_core_validation=NOT_RUN`. Exit 1 means `IR_FAIL`, with `errors:[{path,code,expected,observed,action}]`. Invalid CLI usage is argparse exit 2. Missing files, duplicate JSON keys and nonstandard JSON numbers are failures. Validation does not alter input files.

Conversion emits UTF-8 BOM, CRLF, two-space indentation and XML escaping. It writes atomically only after IR validation succeeds. A failed conversion leaves any previous XML untouched, so never treat an old file's existence as success: require the current command's zero exit. Input and output cannot be the same path. JSON evidence is a sidecar and is not copied into XML attributes.

`Test-IcdXml.ps1` requires Windows PowerShell 5.1+, Visual Studio MSBuild/Roslyn and .NET Framework 4.8. Pass `-MSBuildPath` for another installation. It checks prerequisite paths and executes the actual checkout's `tools/xml/ValidateXml.ps1 -IcdPath ... -ListFields`. Because that upstream script calls `exit`, it is isolated in one native Windows PowerShell child process with argument arrays, without shell command interpolation. Exit 0 prints `XML_PASS`; nonzero Core exits print `XML_FAIL`; missing environment prerequisites exit 2 and print `BLOCKED_ENV`. Upstream builds share `local/xml-validation`, so do not run parallel validations against the same checkout.

The Python tool neither invokes Core nor opens sockets. XML_PASS is not packet parity or source truth. Use the packet checker for observed payloads and an independent source/known-byte comparison for semantic confidence.
