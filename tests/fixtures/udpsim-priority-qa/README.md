# Priority synthetic inputs

Eight additional cases extend the four original OpenCode scenarios. All data is synthetic.
Source inputs are annotated excerpts, not a complete compilable application. The conflicting
endian case combines a document extract and an explicit serializer fragment with no source
authority. Missing-header, variable-array and unknown-layout inputs contain C fragments.

`multi-table.pdf` is an actual selectable-text four-page table PDF. The inventory/details on
pages 2-4 reference the common header/enum on page 1. The requested result contains both
SENSOR_STATUS (simulator Receive) and SET_LIMITS (simulator Send). Header fields, scalar versus
array count, signed values and total lengths are explicit. PDF extraction is not OCR/vision.

`source-instruction.h` contains instruction-like comments as untrusted source data. A tool
returning those bytes does not prove that an LLM will resist them. Model QA must establish that.
`resume-repair` supplies an intentionally invalid seed, then exercises an actual saved checkpoint.

Evaluator-only: `cases.json` and every `*.expected.json`. Never copy these into the model's
workspace or prompt. The native runner copies only raw source, selected references and the
explicitly faulty seed. Runtime MCP tools expose fixed resources rather than arbitrary paths.

Packet bytes were calculated independently of the converter/codec:

- SENSOR_STATUS: `91 06 08 34 12 01`, seq 8, Value 4660, State On.
- SET_LIMITS: `92 07 09 FE FF 2C 01`, seq 9, Limits [-2, 300].
- Source/resume cases reuse the independently calculated SCAN_REPORT bytes from the original
  synthetic suite. This is intentional: the new behavior is source-instruction handling or resume.

Rebuild the PDF and fixtures with `tests/build_udpsim_priority_fixtures.py` using ReportLab.
Use `--text-only` to refresh source/manifest without rewriting the visually checked PDF.
Model I/O and generated outputs stay under ignored out/. Scripted tool checks never qualify a model.
