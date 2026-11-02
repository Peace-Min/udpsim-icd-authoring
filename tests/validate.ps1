[CmdletBinding()]
param(
    [string]$UdpSimRoot,
    [string]$PythonPath = 'python'
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousQaRoot = $env:UDPSIM_QA_ROOT
Push-Location $repoRoot
try {
    foreach ($folder in @('skills', 'tools', 'tests')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $repoRoot $folder) -Filter *.ps1 -Recurse -File) {
            $tokens = $null; $parseErrors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
            if ($parseErrors.Count) { throw "PowerShell syntax failure: $($file.FullName)" }
        }
    }
    if ($UdpSimRoot) { $env:UDPSIM_QA_ROOT = (Resolve-Path -LiteralPath $UdpSimRoot).Path }
    & $PythonPath -X utf8 -m unittest discover -s tests -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Python regression failed.' }
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        & claude plugin validate .claude-plugin/plugin.json
        if ($LASTEXITCODE -ne 0) { throw 'Plugin manifest failed.' }
        & claude plugin validate .claude-plugin/marketplace.json
        if ($LASTEXITCODE -ne 0) { throw 'Marketplace manifest failed.' }
    } else { Write-Output 'NOT_RUN: Claude CLI manifest validation, CLI unavailable.' }
    if ($UdpSimRoot) {
        & (Join-Path $PSScriptRoot 'validate-udpsim.ps1') -UdpSimRoot $env:UDPSIM_QA_ROOT -PythonPath $PythonPath
        if ($LASTEXITCODE -ne 0) { throw 'Actual Core/payload regression failed.' }
        & $PythonPath -X utf8 (Join-Path $PSScriptRoot 'validate_scenarios.py') --udpsim-root $env:UDPSIM_QA_ROOT
        if ($LASTEXITCODE -ne 0) { throw 'Actual scenario context/generation/Core regression failed.' }
    } else { Write-Output 'NOT_RUN: Core regression, supply -UdpSimRoot.' }
    Write-Output 'STANDALONE_CHECKS_PASS: inspect unittest skips and NOT_RUN lines for the exact scope.'
} catch {
    Write-Output ('STANDALONE_CHECKS_FAIL: ' + $_.Exception.Message)
    exit 1
} finally {
    $env:UDPSIM_QA_ROOT = $previousQaRoot
    Pop-Location
}
