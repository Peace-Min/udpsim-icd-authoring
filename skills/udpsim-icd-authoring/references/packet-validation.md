# UDP payload validation

Use this only when the user supplies actual UDP payload bytes. The tool decodes one payload with the current UdpSim Core `MessageCodec`, shows byte offsets and raw bytes, and optionally compares expected field values. It does not open sockets, capture network traffic, parse PCAP/PCAPNG, or prove the peer accepted a command.

## Requirements and inputs

Windows PowerShell 5.1+, .NET Framework 4.8 and Visual Studio MSBuild/Roslyn are required. Supply an explicit UdpSim checkout containing `tools/xml/ValidateXml.ps1`; no downloads or package installation occur. The tool first runs that real authoring validator, builds current Core, and compiles a small helper in a fresh local temporary directory. Do not run validators concurrently against the same UdpSim checkout.

- `-IcdPath`: validated message definition.
- `-PayloadPath`: **UDP payload only**, excluding Ethernet/IP/UDP headers. `-Format hex` accepts hex digits separated by whitespace or colons, without offsets/ASCII columns/`0x` prefixes. `-Format binary` reads raw bytes. Maximum payload size is 65,507 bytes.
- `-Message`: exact expected message code. A valid payload for a different known message fails.
- `-ExpectedPath`: optional JSON object mapping editable leaf paths to **string** values. Numeric strings, signed decimals, hexadecimal bit patterns and enum names use Core `ValueText` semantics. Automatic id/length/seq headers are not editable expectations; id/length are decoded automatically, and `-ExpectedSeq` compares sequence explicitly.
- `-ReportPath`: optional `.json` report outside the UdpSim checkout and skill implementation directory. Must not overwrite any input or traverse symlinks/junctions. A preflight/build failure updates a safely validated destination to `PACKET_FAIL`, replacing any stale successful report. Reports can contain sensitive field names and payload values; keep them in an approved private directory or ignored skill-bank `out/`, not Git. Always check the current process exit code as well as the report.
- `-MSBuildPath`: optional override for a different installed Visual Studio MSBuild path.

```powershell
& '<skill-dir>/scripts/Test-UdpPayload.ps1' -UdpSimRoot 'C:/work/UdpSim' -IcdPath 'C:/private/device.icd.xml' -PayloadPath 'C:/private/tx.hex' -Message SET_CHANNELS -ExpectedPath 'C:/private/expected.json' -ExpectedSeq 3 -ReportPath 'C:/private/packet-result.json'
```

Example expectations, independent synthetic names:

```json
{"Source":"7","Channels[0].Reading":"-5","Channels[0].Flags.Ready":"On"}
```

To export a payload from Wireshark, select the intended UDP datagram and export/copy **the UDP Data bytes**, not the entire frame. If an approved offline `tshark` installation is already available, `tshark -r capture.pcapng -Y "udp && frame.number == 42" -T fields -e udp.payload` produces hex text for that selected packet. Confirm exactly one matching datagram; multiple output lines would otherwise concatenate into one invalid input. `tshark` is an optional external extraction tool, not a bundled dependency. Retain capture timestamp, source/destination endpoints and frame number separately as provenance.

## Verdicts

- `PACKET_DECODE_PASS`: message ID and frame lengths match the supplied ICD and Core decoded fields. No field-value parity was established without expectations.
- `PACKET_EXPECTED_SUBSET_MATCH`: all supplied expectations match, but some editable leaves were not compared.
- `PACKET_EXPECTED_MATCH`: every body leaf and manual header leaf has an explicit matching expectation. Automatic id/length match structurally; SEQ is compared only when `-ExpectedSeq` is supplied. Undeclared Bits positions are not independently checked by Core.
- `PACKET_FAIL`: malformed bytes/ICD, wrong message, bad length, invalid expectation, value mismatch, missing prerequisite or tool failure. Nonzero exit; never report a packet match.

The JSON includes `fields` rows with path, type, byte offset, size, bit width/range, raw bytes, raw integer, decoded value/text and header role. Enum values not declared by the ICD are warnings, consistent with Core reception; an explicit expectation can still compare a numeric value within the field width. Structural decode success does not establish that the ICD itself correctly represents the original specification.

Do not change the ICD merely to fit a captured packet. Compare the specification/source evidence, capture direction and version first. An unresolved disagreement stops the correction loop for user clarification. Payload-only comparison cannot determine network endpoint direction or prove packet arrival at the remote host.
