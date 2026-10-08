param()
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop ontbreekt. Dit is een technische eerste pakketversie, nog geen Docker-vrije standalone.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is niet gestart.' }
$required = @('inhuis-standalone-postgres:local','inhuis-standalone-backend:local','inhuis-standalone-frontend:local')
foreach ($name in $required) {
  docker image inspect $name *> $null
  if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'images.tar'))) { throw "Ontbrekend Docker-image: $name (images.tar ontbreekt)." }
    docker load -i (Join-Path $PSScriptRoot 'images.tar')
    if ($LASTEXITCODE -ne 0) { throw 'Importeren van Docker-images is mislukt.' }
    break
  }
}
docker compose -f docker-compose.yml up -d
if ($LASTEXITCODE -ne 0) { throw 'InHuis kon niet gestart worden.' }
Write-Host 'InHuis wordt gestart op http://localhost:5174'
Start-Process 'http://localhost:5174'
