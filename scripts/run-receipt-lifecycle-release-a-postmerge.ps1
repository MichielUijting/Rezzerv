CLS
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& "$ScriptRoot\run-receipt-lifecycle-release-a.ps1" `
    -PostMerge `
    -ExpectedCommit "95a351ef08e2ab199dfff2df38f65f59254edb64"
