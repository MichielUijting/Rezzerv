$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Deze actie stopt InHuis en verwijdert alle lokale tijdelijke testdata uit dit pakket.'
$answer = Read-Host 'Typ VERWIJDEREN om door te gaan'
if ($answer -cne 'VERWIJDEREN') { Write-Host 'Geannuleerd.'; exit 0 }
if (Get-Command docker -ErrorAction SilentlyContinue) {
  docker compose -f docker-compose.yml down --remove-orphans
  if ($LASTEXITCODE -ne 0) { throw 'Containers konden niet worden gestopt; er is niets verwijderd.' }
}
$data = Join-Path $PSScriptRoot 'data'
if (Test-Path -LiteralPath $data) {
  $item = Get-Item -LiteralPath $data -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Data-map is een koppeling. Verwijdering geweigerd.' }
  Remove-Item -LiteralPath $data -Recurse -Force
}
Write-Host 'Tijdelijke data zijn verwijderd. Verwijder nu de uitgepakte InHuis-map om ook de programmabestanden te wissen.'
