$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'Host-Network-Identity.ps1')
$checks=0
function Assert-Match([string]$Database,[string[]]$Containers,[bool]$Expected) {
    $actual=Test-InhuisDatabaseServerAddress -DatabaseAddress $Database -ContainerAddresses $Containers
    if ($actual -ne $Expected) { throw "Unexpected IP comparison: $Database" }
    $script:checks++
}
function Assert-Rejected([string]$Database,[string[]]$Containers) {
    $rejected=$false
    try { [void](Test-InhuisDatabaseServerAddress -DatabaseAddress $Database -ContainerAddresses $Containers) } catch { $rejected=$true }
    if (-not $rejected) { throw "Invalid IP accepted: $Database" }
    $script:checks++
}
Assert-Match '192.0.2.7/32' @('192.0.2.7') $true
Assert-Match '192.0.2.7' @('192.0.2.7') $true
Assert-Match '192.0.2.7/24' @('192.0.2.8') $false
Assert-Match '192.0.2.7/0' @('198.51.100.7') $false
Assert-Match '192.0.2.7/32' @('198.51.100.7','192.0.2.7') $true
Assert-Match '2001:db8::7/128' @('2001:0db8:0:0:0:0:0:7') $true
Assert-Match '2001:db8::7/64' @('2001:db8::8') $false
Assert-Match '2001:db8::7/128' @('192.0.2.7') $false
Assert-Match '::ffff:192.0.2.7/128' @('192.0.2.7') $false
foreach($value in @('not-an-ip','localhost','192.0.2.7/33','2001:db8::7/129','192.0.2.7/-1','192.0.2.7/032','192.0.2.7/','192.0.2.7/32/1','192.0.2.7:5432','192.0.2.7 ','127.1','0x7f000001','0177.0.0.1','fe80::7%3')) {
    Assert-Rejected $value @('192.0.2.7')
}
Assert-Rejected '192.0.2.7/32' @('not-an-ip')
Assert-Rejected '192.0.2.7/32' @()
Assert-Rejected '192.0.2.7/32' @('')
Write-Host "HOST_NETWORK_IDENTITY_GREEN: $checks checks; no Docker, host probe or production actions executed."
