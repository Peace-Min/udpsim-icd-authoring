[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [Parameter(Mandatory = $true)][string]$ScenarioPath,
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
try {
    $validator = Join-Path $UdpSimRoot 'tools/xml/ValidateXml.ps1'
    $compiler = Join-Path (Split-Path -Parent $MSBuildPath) 'Roslyn/csc.exe'
    $coreProject = Join-Path $UdpSimRoot 'src/UdpSim.Core/UdpSim.Core.csproj'
    foreach ($path in @($validator, $ConfigPath, $ScenarioPath, $MSBuildPath, $compiler, $coreProject)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required input/tool unavailable: $path" }
    }
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validator -ConfigPath ([IO.Path]::GetFullPath($ConfigPath)) -ScenarioPath ([IO.Path]::GetFullPath($ScenarioPath)) -StrictConfig -MSBuildPath $MSBuildPath
        $scenarioExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($scenarioExit -ne 0) { Write-Output "SCENARIO_FAIL: actual Core/strict Config exit $scenarioExit"; exit 1 }
    Write-Output 'SCENARIO_PASS: actual Core Config/ICD/Scenario validation exit 0; no sockets opened.'
    exit 0
} catch {
    Write-Output ('BLOCKED_ENV: ' + $_.Exception.Message)
    exit 2
}
