[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [Parameter(Mandatory = $true)][string]$IcdPath,
    [string]$MSBuildPath = 'C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe'
)
$ErrorActionPreference = 'Stop'
try {
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or newer is required.' }
    $validator = Join-Path $UdpSimRoot 'tools/xml/ValidateXml.ps1'
    foreach ($item in @($validator, $IcdPath, $MSBuildPath)) {
        if (-not (Test-Path -LiteralPath $item -PathType Leaf)) { throw "Required file not found: $item" }
    }
    $compiler = Join-Path (Split-Path -Parent $MSBuildPath) 'Roslyn/csc.exe'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw "Roslyn compiler not found: $compiler" }
    $nativePowerShell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if (-not (Test-Path -LiteralPath $nativePowerShell -PathType Leaf)) { throw 'Windows PowerShell executable not found.' }
    # The upstream validator calls exit, so isolate it in a native PowerShell process.
    $savedErrorPreference = $ErrorActionPreference
    try {
        # Validation errors on native stderr are expected; judge the child exit code.
        $ErrorActionPreference = 'Continue'
        & $nativePowerShell -NoProfile -ExecutionPolicy Bypass -File $validator -IcdPath ([IO.Path]::GetFullPath($IcdPath)) -ListFields -MSBuildPath $MSBuildPath
        $validationExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $savedErrorPreference
    }
    if ($validationExit -ne 0) {
        Write-Output "XML_FAIL: Core validator exit $validationExit"
        exit $validationExit
    }
    Write-Output 'XML_PASS: actual UdpSim authoring validator exited 0; no sockets opened.'
    exit 0
} catch {
    Write-Output ("BLOCKED_ENV: " + $_.Exception.Message)
    exit 2
}
