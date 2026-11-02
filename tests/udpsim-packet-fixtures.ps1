[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $repoRoot 'skills/udpsim-icd-authoring/scripts/Test-UdpPayload.ps1'
$folder = Join-Path $repoRoot ('out/udpsim-packet-tests-' + [Guid]::NewGuid().ToString('N') + '/space path')
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$icd = Join-Path $folder 'synthetic.icd.xml'
$utf8 = New-Object Text.UTF8Encoding($false)
$xml = @'
<Icd name="Synthetic packet test" endian="little">
  <Enums><Enum name="Ready"><Item name="Off" value="0"/><Item name="On" value="1"/></Enum></Enums>
  <Types><Struct name="Channel"><Field name="Reading" type="int16"/><Field name="Flags" type="uint8"><Bits name="Ready" from="0" to="0" enum="Ready"/><Bits name="Mode" from="1" to="2"/></Field></Struct></Types>
  <Header><Field name="Id" type="uint16" role="id"/><Field name="Length" type="uint16" role="length"/><Field name="Seq" type="uint16" role="seq"/><Field name="Source" type="uint8"/></Header>
  <Send><Message code="SET" id="0x7101" name="Set" length="13"><Field name="Channels" type="Channel" count="2"/></Message></Send>
  <Receive><Message code="REPORT" id="0x7201" name="Report" length="13"><Field name="Channels" type="Channel" count="2"/></Message></Receive>
</Icd>
'@
[IO.File]::WriteAllText($icd, $xml, $utf8)
$hexPath = Join-Path $folder 'payload.hex'
[IO.File]::WriteAllText($hexPath, '01 71 0d 00 03 00 07 fb ff 05 12 00 05', $utf8)
$expectedPath = Join-Path $folder 'expected.json'
[IO.File]::WriteAllText($expectedPath, '{"Source":"7","Channels[0].Reading":"-5","Channels[0].Flags.Ready":"On","Channels[0].Flags.Mode":"2","Channels[1].Reading":"18","Channels[1].Flags.Ready":"On","Channels[1].Flags.Mode":"2"}', $utf8)
$report = Join-Path $folder 'report.json'
$passed = 0
function Invoke-Case {
    param([string]$Name, [bool]$ShouldPass, [string]$Payload = $hexPath, [string]$Code = 'SET', [string]$Expected = $expectedPath, [string]$PayloadFormat = 'hex')
    $args = @{ UdpSimRoot = $UdpSimRoot; IcdPath = $icd; PayloadPath = $Payload; Message = $Code; Format = $PayloadFormat; MSBuildPath = $MSBuildPath; ReportPath = $report }
    if ($Expected) { $args.ExpectedPath = $Expected }
    & $tool @args *> (Join-Path $folder ($Name + '.txt'))
    $actualPass = $LASTEXITCODE -eq 0
    if ($actualPass -ne $ShouldPass) { throw "FAIL $Name expected pass=$ShouldPass, exit=$LASTEXITCODE. Evidence: $folder" }
    $script:passed++
    Write-Output "PASS $Name"
}
Invoke-Case 'nested-signed-bits-enum-full' $true
$parsed = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
if ($parsed.status -ne 'PACKET_EXPECTED_MATCH') { throw 'Full comparison status mismatch.' }
$reading = $parsed.fields | Where-Object { $_.path -eq 'Channels[0].Reading' }
if ($reading.offset -ne 7 -or $reading.value -ne -5 -or $reading.raw_bytes -ne 'FB FF') { throw 'Decoded field evidence is incorrect.' }
$passed++
Write-Output 'PASS offset-raw-value-evidence'
Invoke-Case 'decode-only' $true -Expected ''
$parsed = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
if ($parsed.status -ne 'PACKET_DECODE_PASS') { throw 'Decode-only was incorrectly labeled value parity.' }
$subset = Join-Path $folder 'subset.json'
[IO.File]::WriteAllText($subset, '{"Channels[0].Reading":"-5"}', $utf8)
Invoke-Case 'subset' $true -Expected $subset
$parsed = Get-Content -Raw -LiteralPath $report | ConvertFrom-Json
if ($parsed.status -ne 'PACKET_EXPECTED_SUBSET_MATCH') { throw 'Subset comparison was incorrectly labeled complete.' }
$badExpected = Join-Path $folder 'wrong.json'
[IO.File]::WriteAllText($badExpected, '{"Channels[0].Reading":"-4"}', $utf8)
Invoke-Case 'wrong-value' $false -Expected $badExpected
[IO.File]::WriteAllText($badExpected, '{"NotAField":"1"}', $utf8)
Invoke-Case 'unknown-expected-field' $false -Expected $badExpected
[IO.File]::WriteAllText($badExpected, '{"Channels[0].Reading":-5}', $utf8)
Invoke-Case 'nonstring-expectation' $false -Expected $badExpected
[IO.File]::WriteAllText($badExpected, '{"Source":"7","Source":"6"}', $utf8)
Invoke-Case 'duplicate-expectation' $false -Expected $badExpected
[IO.File]::WriteAllText($badExpected, '{"Channels[0].Reading":"99999"}', $utf8)
Invoke-Case 'out-of-range-expectation' $false -Expected $badExpected
Invoke-Case 'wrong-message-direction' $false -Code 'REPORT'
$badPayload = Join-Path $folder 'bad.hex'
[IO.File]::WriteAllText($badPayload, '01 71 0c 00 03 00 07 fb ff 05 12 00 05', $utf8)
Invoke-Case 'header-length' $false -Payload $badPayload
[IO.File]::WriteAllText($badPayload, '01 71 0d 00 03 00 07 fb ff 05 12 00', $utf8)
Invoke-Case 'truncated' $false -Payload $badPayload
[IO.File]::WriteAllText($badPayload, 'ff ff 0d 00 03 00 07 fb ff 05 12 00 05', $utf8)
Invoke-Case 'unknown-id' $false -Payload $badPayload
[IO.File]::WriteAllText($badPayload, '01 7', $utf8)
Invoke-Case 'odd-hex' $false -Payload $badPayload
[IO.File]::WriteAllText($badPayload, 'not hex', $utf8)
Invoke-Case 'invalid-hex' $false -Payload $badPayload
$binary = Join-Path $folder 'payload.bin'
[IO.File]::WriteAllBytes($binary, [byte[]]@(1,113,13,0,3,0,7,251,255,5,18,0,5))
Invoke-Case 'binary' $true -Payload $binary -PayloadFormat 'binary'
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ExpectedSeq 3 -MSBuildPath $MSBuildPath *> (Join-Path $folder 'seq-good.txt')
if ($LASTEXITCODE -ne 0) { throw 'Matching seq failed.' }
$passed++
Write-Output 'PASS seq-match'
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ExpectedSeq 4 -MSBuildPath $MSBuildPath *> (Join-Path $folder 'seq-wrong.txt')
if ($LASTEXITCODE -eq 0) { throw 'Mismatching seq passed.' }
$passed++
Write-Output 'PASS seq-mismatch'
$bigIcd = $xml.Replace('endian="little"', 'endian="big"')
[IO.File]::WriteAllText($icd, $bigIcd, $utf8)
[IO.File]::WriteAllText($hexPath, '71 01 00 0d 00 03 07 ff fb 05 00 12 05', $utf8)
Invoke-Case 'big-endian' $true
[IO.File]::WriteAllText($icd, $xml, $utf8)
[IO.File]::WriteAllText($hexPath, '01 71 0d 00 03 00 07 fb ff 05 12 00 05', $utf8)
$original = [IO.File]::ReadAllText($hexPath)
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ReportPath $hexPath -MSBuildPath $MSBuildPath *> (Join-Path $folder 'overwrite.txt')
if ($LASTEXITCODE -eq 0 -or [IO.File]::ReadAllText($hexPath) -ne $original) { throw 'Report input overwrite protection failed.' }
$passed++
Write-Output 'PASS report-overwrite-refused'
$stale = '{"status":"PACKET_EXPECTED_MATCH"}'
[IO.File]::WriteAllText($report, $stale, $utf8)
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath (Join-Path $folder 'missing.hex') -Message SET -ReportPath $report -MSBuildPath $MSBuildPath *> (Join-Path $folder 'missing-input.txt')
if ($LASTEXITCODE -eq 0 -or (Get-Content -Raw -LiteralPath $report | ConvertFrom-Json).status -ne 'PACKET_FAIL') { throw 'Missing input left stale success report.' }
$passed++
Write-Output 'PASS stale-report-missing-input'
[IO.File]::WriteAllText($report, $stale, $utf8)
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ReportPath $report -MSBuildPath (Join-Path $folder 'missing-msbuild.exe') *> (Join-Path $folder 'missing-build-tool.txt')
if ($LASTEXITCODE -eq 0 -or (Get-Content -Raw -LiteralPath $report | ConvertFrom-Json).status -ne 'PACKET_FAIL') { throw 'Missing tool left stale success report.' }
$passed++
Write-Output 'PASS stale-report-missing-tool'
[IO.File]::WriteAllText($report, $stale, $utf8)
[IO.File]::WriteAllText($icd, '<Icd name="Invalid"/>', $utf8)
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ReportPath $report -MSBuildPath $MSBuildPath *> (Join-Path $folder 'invalid-icd.txt')
if ($LASTEXITCODE -eq 0 -or (Get-Content -Raw -LiteralPath $report | ConvertFrom-Json).status -ne 'PACKET_FAIL') { throw 'Invalid ICD left stale success report.' }
[IO.File]::WriteAllText($icd, $xml, $utf8)
$passed++
Write-Output 'PASS stale-report-invalid-icd'
$inputJson = [IO.File]::ReadAllText($expectedPath)
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ExpectedPath $expectedPath -ReportPath $expectedPath -MSBuildPath $MSBuildPath *> (Join-Path $folder 'expected-overwrite.txt')
if ($LASTEXITCODE -eq 0 -or [IO.File]::ReadAllText($expectedPath) -ne $inputJson) { throw 'Expected JSON overwrite protection failed.' }
$passed++
Write-Output 'PASS expectation-overwrite-refused'
$protectedReport = Join-Path $UdpSimRoot 'tools/xml/packet-protected.json'
& $tool -UdpSimRoot $UdpSimRoot -IcdPath $icd -PayloadPath $hexPath -Message SET -ReportPath $protectedReport -MSBuildPath $MSBuildPath *> (Join-Path $folder 'protected-destination.txt')
if ($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $protectedReport)) { throw 'Protected UdpSim destination accepted.' }
$passed++
Write-Output 'PASS implementation-report-refused'
Write-Output "PASS packet fixtures: $passed checks. Generated evidence: $folder"
exit 0
