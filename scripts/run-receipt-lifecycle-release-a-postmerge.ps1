CLS
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
Set-Location $ProjectRoot

git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw "git fetch origin mislukt"
}

$ExpectedCommit = (git rev-parse origin/main).Trim()
if (-not $ExpectedCommit) {
    throw "origin/main kon niet worden bepaald"
}

Write-Host "[INFO] Te controleren actuele origin/main: $ExpectedCommit" -ForegroundColor Cyan

& "$ScriptRoot\run-receipt-lifecycle-release-a.ps1" `
    -PostMerge `
    -ExpectedCommit $ExpectedCommit
