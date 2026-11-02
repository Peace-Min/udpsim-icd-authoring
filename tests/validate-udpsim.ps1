[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [string]$PythonPath = 'python',
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
$bankRoot = Split-Path -Parent $PSScriptRoot
$evidence = Join-Path $bankRoot ('out/udpsim-qa-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
$results = @()
try {
    $pythonCommand = Get-Command $PythonPath -ErrorAction Stop
    & $pythonCommand.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required; provision it before offline transfer.' }
    $parseErrors = @()
    foreach ($file in @(Get-ChildItem (Join-Path $bankRoot 'skills/udpsim-icd-authoring/scripts') -Filter *.ps1 -File) + @(Get-Item $PSCommandPath)) {
        $tokens = $null; $errors = $null
        [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) | Out-Null
        $parseErrors += $errors
    }
    if ($parseErrors.Count) { throw ('PowerShell parser failure: ' + ($parseErrors -join '; ')) }
    Push-Location $bankRoot
    try {
        foreach ($suite in @('test_udpsim_ir.py', 'test_udpsim_model_eval.py')) {
            $log = Join-Path $evidence ($suite + '.txt')
            # Native test failures write stderr; the process exit is the verdict.
            $savedPreference = $ErrorActionPreference
            try {
                $ErrorActionPreference = 'Continue'
                & $pythonCommand.Source -m unittest discover -s tests -p $suite *> $log
                $testExit = $LASTEXITCODE
            } finally { $ErrorActionPreference = $savedPreference }
            $results += @{ suite = $suite; exit = $testExit; log = [IO.Path]::GetFileName($log) }
            if ($testExit -ne 0) { throw "Failed $suite; inspect $log" }
        }
        $packetLog = Join-Path $evidence 'packets.txt'
        & (Join-Path $PSScriptRoot 'udpsim-packet-fixtures.ps1') -UdpSimRoot $UdpSimRoot -MSBuildPath $MSBuildPath *> $packetLog
        $packetExit = $LASTEXITCODE
        $results += @{ suite = 'packet fixtures'; exit = $packetExit; log = 'packets.txt' }
        if ($packetExit -ne 0) { throw "Packet fixtures failed; inspect $packetLog" }
    } finally { Pop-Location }
    $summary = @{ status = 'LOCAL_TOOLS_PASS'; results = $results; cloud_model = 'NOT_RUN'; internal_target = 'NOT_RUN' }
    $summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'summary.json') -Encoding UTF8
    Write-Output "LOCAL_TOOLS_PASS $evidence"
} catch {
    @{ status = 'LOCAL_TOOLS_FAIL'; error = $_.Exception.Message; results = $results; cloud_model = 'NOT_RUN'; internal_target = 'NOT_RUN' } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'summary.json') -Encoding UTF8
    Write-Output ('LOCAL_TOOLS_FAIL ' + $_.Exception.Message)
    exit 1
}
