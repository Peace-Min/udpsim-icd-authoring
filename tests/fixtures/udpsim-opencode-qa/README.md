# Fresh synthetic OpenCode Skill QA fixtures

These independently written inputs contain no operational ICD or derived company data.
They intentionally differ from the existing PING examples in the Skill reference.

Copy only `scan-report.h`, `document.pdf`, and `missing-endian.h` into the model
workspace. `cases.json` is evaluator-only: it contains expected definitions, known bytes and
expected values. Do not show it or its correct `expected` values to the model.

The repair task additionally provides `scan-report.bad-length.json`, an intentionally faulty
seed definition with declared length 16 instead of the source's 17. It is explicitly a faulty
input, not an accepted answer. The source remains authoritative. Do not provide its corrected
oracle to the model. The seed must fail the unchanged intermediate validator before repair.

`document.pdf` is an actual three-page selectable-text PDF, generated from the synthetic
`window-spec-excerpt.txt` with `tests/build_udpsim_qa_pdf.py` (ReportLab required only to rebuild).
The evaluator uses pypdf text extraction with physical page markers. The requested inventory/detail
on pages 2-3 depends on the common header/enum on page 1. This does not qualify scanned PDF OCR
or native model vision. The parent extracts all three pages for this small dependency fixture.

`cases.json` contract:

- `schema_version`: 1.
- `cases`: list of `id`, `input`, `kind`, `expected` (canonical semantic IR subset).
- `kind`: `positive`, `ambiguous`, or `repair`.
- `request`: extraction scope and simulator-role request given with the input.
- `payload_hex`, `expected_values`, `packet_message`: independent packet oracle for accepted definitions.
- `seed_input`: faulty seed to provide only for the repair task.
- `missing_facts`: required unavailable facts for an ambiguity stop.

The positive cases include an `expected` definition without `evidence` because source locators
are model-authored and are checked separately for traceability. Require all expected semantic
facts plus valid nonempty evidence and an empty unresolved list. Names/type definitions are
explicit in the source; do not relax wrong wire facts merely because XML validation passes.

For ambiguity, `expected` omits the unknown byte order. Require `unresolved` to name byte order,
do not accept a guessed `big` or `little`, and require no accepted final XML.

Hand-calculated packet checks:

- SCAN_REPORT: header `4A31 0011 05`, then slots `FED4 07 05`, `04D2 00 02`,
  `FFFF FF 07`. Bias values are -300, 1234, -1; Flags encode Active bit 0 and Quality bits 1..2.
- SET_WINDOW: header `67 08 0B`, then `3412 CDAB 01` in little endian. Counter=11,
  Limits=[0x1234,0xABCD], Enabled=Running.

Expected packet values are strings so they can be passed to `Test-UdpPayload.ps1 -ExpectedPath`.
