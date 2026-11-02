[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [Parameter(Mandatory = $true)][string]$IcdPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath,
    [Parameter(Mandatory = $true)][string]$Message,
    [ValidateSet('hex', 'binary')][string]$Format = 'hex',
    [string]$ExpectedPath,
    [Nullable[long]]$ExpectedSeq,
    [string]$ReportPath,
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
$safeReport = $null
try {
    if ($ReportPath) {
        $candidate = [IO.Path]::GetFullPath($ReportPath)
        if ([IO.Path]::GetExtension($candidate) -ine '.json') { throw 'ReportPath must have a .json extension.' }
        foreach ($inputPath in @($IcdPath, $PayloadPath, $ExpectedPath, $MSBuildPath)) {
            if ($inputPath -and [string]::Equals($candidate, [IO.Path]::GetFullPath($inputPath), [StringComparison]::OrdinalIgnoreCase)) { throw 'ReportPath must not overwrite an input or tool file.' }
        }
        $skillRoot = Split-Path -Parent $PSScriptRoot
        foreach ($protectedRoot in @($UdpSimRoot, $skillRoot)) {
            $rootPath = [IO.Path]::GetFullPath($protectedRoot).TrimEnd([char[]]'\/')
            if ([string]::Equals($candidate, $rootPath, [StringComparison]::OrdinalIgnoreCase) -or $candidate.StartsWith($rootPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'ReportPath must be outside the UdpSim checkout and the skill implementation directory.'
            }
        }
        # A failed run must never leave a previous successful machine report in place.
        # Establish a safe destination before any input resolution or build can fail.
        $pathToCheck = $candidate
        while ($pathToCheck) {
            if (Test-Path -LiteralPath $pathToCheck) {
                $item = Get-Item -LiteralPath $pathToCheck -Force
                if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'ReportPath must not traverse symbolic links or junctions.' }
            }
            $pathToCheck = Split-Path -Parent $pathToCheck
        }
        $safeReport = $candidate
    }
    $repo = (Resolve-Path -LiteralPath $UdpSimRoot).Path
    $icd = (Resolve-Path -LiteralPath $IcdPath).Path
    $payload = (Resolve-Path -LiteralPath $PayloadPath).Path
    $validator = Join-Path $repo 'tools/xml/ValidateXml.ps1'
    if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) { throw 'UdpSimRoot must contain tools/xml/ValidateXml.ps1.' }
    if (-not (Test-Path -LiteralPath $MSBuildPath -PathType Leaf)) { throw 'MSBuild is unavailable. Supply -MSBuildPath to an offline Visual Studio MSBuild installation.' }
    $compiler = Join-Path (Split-Path -Parent $MSBuildPath) 'Roslyn/csc.exe'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'Roslyn/csc.exe is unavailable beside MSBuild. Install the offline Visual Studio C# build tools.' }
    $expected = $null
    if ($ExpectedPath) { $expected = (Resolve-Path -LiteralPath $ExpectedPath).Path }
    # The upstream script builds the current Core and applies additional authoring checks.
    # Do not run this command concurrently against the same UdpSim checkout.
    & $validator -IcdPath $icd -MSBuildPath $MSBuildPath
    if ($LASTEXITCODE -ne 0) { throw 'ICD authoring validation failed. Packet comparison was not run.' }
    $coreDll = Join-Path $repo 'local/xml-validation/UdpSim.Core.dll'
    $buildFolder = Join-Path ([IO.Path]::GetTempPath()) ('udpsim-packet-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $buildFolder | Out-Null
    Copy-Item -LiteralPath $coreDll -Destination $buildFolder
    $exe = Join-Path $buildFolder 'PacketCheck.exe'
    & $compiler /nologo /r:System.Core.dll /r:System.Web.Extensions.dll "/r:$coreDll" "/out:$exe" (Join-Path $PSScriptRoot 'PacketCheck.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Packet helper compilation failed.' }
    $packetArgs = @('--icd', $icd, '--payload', $payload, '--format', $Format, '--message', $Message)
    if ($expected) { $packetArgs += @('--expected', $expected) }
    if ($null -ne $ExpectedSeq) { $packetArgs += @('--seq', $ExpectedSeq.ToString([Globalization.CultureInfo]::InvariantCulture)) }
    if ($safeReport) { $packetArgs += @('--report', $safeReport) }
    & $exe @packetArgs
    $packetExit = $LASTEXITCODE
    exit $packetExit
}
catch {
    $failure = $_.Exception.Message
    if ($safeReport) {
        try {
            [IO.Directory]::CreateDirectory((Split-Path -Parent $safeReport)) | Out-Null
            $failureJson = @{ status = 'PACKET_FAIL'; errors = @($failure); fields = @(); warnings = @() } | ConvertTo-Json -Depth 4
            [IO.File]::WriteAllText($safeReport, $failureJson, (New-Object Text.UTF8Encoding($false)))
        }
        catch { Write-Output ('FAIL Could not update failure report: ' + $_.Exception.Message) }
    }
    Write-Output ('FAIL Packet validation: ' + $failure)
    exit 1
}
