[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [string]$IcdKey,
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
try {
    $app = (Resolve-Path -LiteralPath $UdpSimRoot).Path
    $config = (Resolve-Path -LiteralPath $ConfigPath).Path
    $output = [IO.Path]::GetFullPath($OutputPath)
    $skillRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\', '/')
    if ([IO.Path]::GetExtension($output) -ine '.json') { throw 'OutputPath must end in .json.' }
    if ($output.StartsWith($skillRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must be outside the Skill implementation.' }
    $validator = Join-Path $app 'tools/xml/ValidateXml.ps1'
    $compiler = Join-Path (Split-Path -Parent $MSBuildPath) 'Roslyn/csc.exe'
    $coreProject = Join-Path $app 'src/UdpSim.Core/UdpSim.Core.csproj'
    foreach ($path in @($validator, $MSBuildPath, $compiler, $coreProject)) { if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required tool unavailable: $path" } }
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $validator -ConfigPath $config -StrictConfig -MSBuildPath $MSBuildPath
        $strictExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($strictExit -ne 0) { Write-Output "CONTEXT_FAIL: strict Config/ICD validation exit $strictExit"; exit 1 }
    $build = Join-Path ([IO.Path]::GetTempPath()) ('udpsim-context-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $build | Out-Null
    $core = Join-Path $app 'local/xml-validation/UdpSim.Core.dll'
    Copy-Item -LiteralPath $core -Destination $build
    $exe = Join-Path $build 'ScenarioContext.exe'
    & $compiler /nologo /r:System.Core.dll /r:System.Web.Extensions.dll "/r:$core" "/out:$exe" (Join-Path $PSScriptRoot 'ScenarioContext.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Scenario context helper compilation failed.' }
    $arguments = @('--config', $config, '--output', $output, '--app', $app, '--skill', $skillRoot)
    if ($IcdKey) { $arguments += @('--icd', $IcdKey) }
    & $exe @arguments
    exit $LASTEXITCODE
} catch {
    Write-Output ('BLOCKED_ENV: ' + $_.Exception.Message)
    exit 2
}
