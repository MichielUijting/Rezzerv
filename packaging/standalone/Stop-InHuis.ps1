$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose -f docker-compose.yml down
if ($LASTEXITCODE -ne 0) { throw 'Stoppen is mislukt.' }
Write-Host 'InHuis is gestopt. Testdata zijn bewaard.'
