[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$HarnessRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ProjectRoot = Split-Path -Parent $HarnessRoot

$RequiredPaths = @(
    'AGENTS.md',
    '.codex/hooks.json',
    '.harness/AGENTS.md',
    '.harness/README.md',
    '.harness/.agent/application-owner.md',
    '.harness/wiki/项目地图.md',
    '.harness/rules/project-boundaries.md',
    '.harness/rules/architecture.md',
    '.harness/rules/verification.md',
    '.harness/rules/frontend.md',
    '.harness/rules/backend.md',
    '.harness/rules/miniprogram.md',
    '.harness/rules/http-api.md',
    '.harness/rules/security.md',
    '.harness/skill/systematic-debugging/SKILL.md',
    '.harness/changes/README.md',
    '.harness/changes/_template/summary.md',
    '.harness/scripts/codex-hook.py',
    'harness.ps1',
    'Taskfile.yml'
)

$Errors = [System.Collections.Generic.List[string]]::new()

function Get-GuideTargets([string]$Guide) {
    $GuidePath = Join-Path $ProjectRoot $Guide
    $Content = Get-Content -LiteralPath $GuidePath -Raw -Encoding UTF8
    foreach ($Link in [regex]::Matches($Content, '\[[^\]\r\n]+\]\(([^)\r\n]+)\)')) {
        $Target = $Link.Groups[1].Value.Trim().Trim('<', '>').Split('#')[0]
        if (-not $Target -or $Target -match '^[a-z][a-z0-9+.-]*:') { continue }
        $FullPath = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $GuidePath) $Target))
        if (-not (Test-Path -LiteralPath $FullPath)) {
            $Errors.Add("Broken link in ${Guide}: $Target")
        }
        $FullPath
    }
}

foreach ($RelativePath in $RequiredPaths) {
    $FullPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
        $Errors.Add("Missing required file: $RelativePath")
    }
}

$RootTargets = @(Get-GuideTargets 'AGENTS.md')
if ((Join-Path $HarnessRoot 'AGENTS.md') -notin $RootTargets) {
    $Errors.Add('Root AGENTS.md does not link to .harness/AGENTS.md')
}

$HarnessTargets = @(Get-GuideTargets '.harness/AGENTS.md')
foreach ($RelativePath in $RequiredPaths) {
    if ($RelativePath -match '^\.harness/(\.agent|rules|wiki)/' -and
        [IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath)) -notin $HarnessTargets) {
        $Errors.Add(".harness/AGENTS.md does not link to: $RelativePath")
    }
}

$SkillsRoot = Join-Path $HarnessRoot 'skill'
if (Test-Path -LiteralPath $SkillsRoot -PathType Container) {
    Get-ChildItem -LiteralPath $SkillsRoot -Directory | ForEach-Object {
        $SkillFile = Join-Path $_.FullName 'SKILL.md'
        if ($SkillFile -notin $HarnessTargets) {
            $Errors.Add("Unregistered project skill in .harness/AGENTS.md: $($_.Name)")
        }
        if (-not (Test-Path -LiteralPath $SkillFile -PathType Leaf)) {
            $Errors.Add("Skill directory has no SKILL.md: $($_.Name)")
            return
        }

        $Content = Get-Content -LiteralPath $SkillFile -Raw -Encoding UTF8
        if ($Content -notmatch "(?ms)\A---\s*.*?^name:\s*([^\r\n]+)\s*$.*?^description:\s*([^\r\n]+)\s*$.*?^---\s*") {
            $Errors.Add("Invalid Skill frontmatter: $($_.Name)/SKILL.md")
            return
        }

        $DeclaredName = $Matches[1].Trim()
        if ($DeclaredName -ne $_.Name) {
            $Errors.Add("Skill name mismatch: directory '$($_.Name)', frontmatter '$DeclaredName'")
        }
    }
}

if ($Errors.Count -gt 0) {
    $Errors | ForEach-Object { Write-Error $_ }
    exit 1
}

$SkillCount = @(Get-ChildItem -LiteralPath $SkillsRoot -Directory).Count
Write-Host "Harness validation passed ($($RequiredPaths.Count) required files, $SkillCount skill)."
exit 0
