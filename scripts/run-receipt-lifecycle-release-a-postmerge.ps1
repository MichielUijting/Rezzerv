CLS
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& "$ScriptRoot\run-receipt-lifecycle-release-a.ps1" `
    -PostMerge `
    -ExpectedCommit "6ea4143c9e430eee1d5ebed190184637c766b9e9"
