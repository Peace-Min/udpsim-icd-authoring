[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$UdpSimRoot,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
try {
    $repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repoRoot 'out/udpsim-transfer' }
    $simRoot = (Resolve-Path -LiteralPath $UdpSimRoot).Path
    $destination = [IO.Path]::GetFullPath($OutputDirectory)
    $bundle = Join-Path $destination ('udpsim-skill-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $bundle -Force | Out-Null
    $paths = @(
        '.claude-plugin',
        'commands/udpsim-icd-authoring.md',
        'README.md',
        'AGENTS.md',
        'PROVENANCE.md',
        '.gitattributes',
        'skills/udpsim-icd-authoring',
        '.claude/skills/udpsim-icd-authoring',
        'docs/wiki/udpsim-icd-authoring.md',
        'docs/wiki/interaction-sequence.md',
        'docs/wiki/scenario-authoring.md',
        'docs/wiki/udpsim-icd-qa.md',
        'docs/wiki/udpsim-cloud-qa.md',
        'docs/wiki/udpsim-free-models.md',
        'docs/wiki/udpsim-opencode-api.md',
        'docs/wiki/udpsim-opencode-skill-qa.md',
        'docs/wiki/udpsim-priority-qa.md',
        'docs/wiki/udpsim-codex-autonomous-qa.md',
        'docs/plans/udpsim-icd-authoring-plan.md',
        'docs/plans/udpsim-opencode-skill-qa-plan.md',
        'docs/plans/udpsim-priority-qa-plan.md',
        'docs/plans/udpsim-cloud-qa-plan.md',
        'docs/plans/standalone-extraction.md',
        'docs/plans/scenario-authoring.md',
        'tests/test_udpsim_ir.py',
        'tests/test_udpsim_model_eval.py',
        'tests/run_udpsim_model_eval.py',
        'tests/run_udpsim_opencode_eval.py',
        'tests/test_udpsim_opencode_eval.py',
        'tests/test_udpsim_opencode_api.py',
        'tests/test_udpsim_native_qa.py',
        'tests/test_udpsim_cloud.py',
        'tests/test_udpsim_cloud_environment.py',
        'tests/validate_udpsim_priority.py',
        'tests/validate_codex_autonomous.py',
        'tests/build_udpsim_qa_pdf.py',
        'tests/build_udpsim_priority_fixtures.py',
        'tests/udpsim-packet-fixtures.ps1',
        'tests/validate-udpsim.ps1',
        'tests/validate.ps1',
        'tests/test_standalone_layout.py',
        'tests/test_scenario_tool.py',
        'tests/validate_scenarios.py',
        'tests/fixtures/udpsim-ir',
        'tests/fixtures/udpsim-model',
        'tests/fixtures/udpsim-opencode-qa',
        'tests/fixtures/udpsim-priority-qa',
        'tests/fixtures/scenarios',
        'tools/udpsim_opencode_api.py',
        'tools/udpsim_agent_mcp.py',
        'tools/udpsim_agent_call.py',
        'tools/udpsim_native_qa.py',
        'tools/udpsim_cloud_environment.py',
        'tools/udpsim_mock_provider.py',
        'tools/Test-UdpSimCloud.py',
        'tools/package-udpsim-skill.ps1',
        '.gitignore',
        'LICENSE'
    )
    # An explicit source allowlist keeps captures, private inputs and model I/O out.
    function Copy-SourceTree([string]$FromRoot, [string]$Relative, [string]$ToRoot) {
        $source = Join-Path $FromRoot $Relative
        if (-not (Test-Path -LiteralPath $source)) { throw "Missing package input: $Relative" }
        $item = Get-Item -LiteralPath $source
        $files = if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $source -File -Recurse } else { @($item) }
        foreach ($file in $files) {
            if ($file.FullName -match '[\\/](bin|obj|__pycache__)[\\/]' -or $file.Extension -in @('.pyc', '.dll', '.exe', '.pdb')) { continue }
            $relativeFile = $file.FullName.Substring($FromRoot.TrimEnd('\', '/').Length + 1)
            $target = Join-Path $ToRoot $relativeFile
            New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
            Copy-Item -LiteralPath $file.FullName -Destination $target
        }
    }
    $skillDestination = Join-Path $bundle 'udpsim-icd-authoring'
    foreach ($path in $paths) { Copy-SourceTree $repoRoot $path $skillDestination }
    foreach ($path in @('src/UdpSim.Core', 'tools/xml', 'docs/wiki', 'samples/authoring')) {
        Copy-SourceTree $simRoot $path (Join-Path $bundle 'UdpSim')
    }
    $skillCommit = & git -C $repoRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record standalone skill baseline commit.' }
    $simCommit = & git -C $simRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record UdpSim baseline commit.' }
    $start = @'
# UdpSim skill test package

This is a curated standalone working-tree snapshot; use per-file hashes for its exact contents.
Open udpsim-icd-authoring in Claude Code, then use /udpsim-icd-authoring.
Give the skill the sibling UdpSim directory as -UdpSimRoot.

Read udpsim-icd-authoring/docs/wiki/udpsim-icd-authoring.md, udpsim-icd-qa.md and scenario-authoring.md.
Prerequisites: Python 3.10+, Windows PowerShell 5.1+, Visual Studio MSBuild/Roslyn,
.NET Framework 4.8. Provision installers separately before entering the air gap.
This package contains no model weights, Python runtime, capture driver or credentials.
PDF extraction/OCR needs an independently provisioned local reader/extractor.
Priority QA PDF fixtures require pypdf; rebuilding their PDFs additionally requires ReportLab.
OpenCode/Bifrost binaries are not included. Cloud/native-MCP instructions describe external QA;
do not run cloud setup/inference in the air gap. See udpsim-priority-qa.md for measured limits.

From udpsim-icd-authoring run:
& ./tests/validate.ps1 -UdpSimRoot ../UdpSim

Do not run Core/packet validations concurrently against the same UdpSim directory.
No cloud 27B or internal target-model acceptance is implied by this package.
The tests/fixtures inputs are synthetic; expected.json is an evaluator-only oracle.
Never show that answer key to the agent being evaluated.
'@
    [IO.File]::WriteAllText((Join-Path $bundle 'START-HERE.md'), $start, (New-Object Text.UTF8Encoding($false)))
    $manifest = [ordered]@{
        format = 2
        skill_baseline = "$skillCommit"
        upstream_skillbank = 'fe485f2a113221a6ba574dfaa939ac7af6fad381'
        udpsim_baseline = "$simCommit"
        snapshot = 'working-tree; use per-file hashes, baseline commit alone is not this snapshot'
        cloud_model_qa = 'NOT_RUN'
        cloud_model_scope = 'same-model Qwen proxy; OpenCode comparison results are separately documented'
        opencode_proxy_qa = 'see docs/wiki/udpsim-opencode-skill-qa.md; packaging does not qualify models'
        native_agent_qa = 'see docs/wiki/udpsim-priority-qa.md; packaging does not qualify models'
        internal_target_qa = 'NOT_RUN'
        files = @(Get-ChildItem -LiteralPath $bundle -File -Recurse | Sort-Object FullName | ForEach-Object {
            [ordered]@{ path = $_.FullName.Substring($bundle.Length + 1).Replace('\', '/'); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
        })
    }
    [IO.File]::WriteAllText((Join-Path $bundle 'manifest.json'), ($manifest | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
    $archive = $bundle + '.zip'
    Compress-Archive -LiteralPath $bundle -DestinationPath $archive
    Write-Output "PACKAGE_READY $archive"
    Write-Output ('SHA256 ' + (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash)
} catch {
    Write-Output ('PACKAGE_FAIL ' + $_.Exception.Message)
    exit 1
}
