param(
  [string]$OutputDirectory = (Join-Path (Get-Location) 'release')
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$packageRoot = Join-Path $OutputDirectory 'InHuis-Standalone'
$zipPath = Join-Path $OutputDirectory 'InHuis-Standalone.zip'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker is nodig op de bouwcomputer.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker Engine is niet beschikbaar.' }
if (Test-Path -LiteralPath $packageRoot) { throw "Pakketmap bestaat al: $packageRoot" }
if (Test-Path -LiteralPath $zipPath) { throw "ZIP bestaat al: $zipPath" }
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
$commit = (git -C $repoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Exacte Git-commit kan niet worden vastgesteld.' }
try {
  docker build -t inhuis-standalone-backend:local (Join-Path $repoRoot 'backend')
  if ($LASTEXITCODE -ne 0) { throw 'Backend build mislukt.' }
  docker build --build-arg "REZZERV_COMMIT=$commit" -t inhuis-standalone-frontend:local (Join-Path $repoRoot 'frontend')
  if ($LASTEXITCODE -ne 0) { throw 'Frontend build mislukt.' }
  docker pull postgres:17-alpine
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL pull mislukt.' }
  docker tag postgres:17-alpine inhuis-standalone-postgres:local
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL tagging mislukt.' }
  docker save -o (Join-Path $packageRoot 'images.tar') inhuis-standalone-backend:local inhuis-standalone-frontend:local inhuis-standalone-postgres:local
  if ($LASTEXITCODE -ne 0) { throw 'Docker-image export mislukt.' }
  foreach ($name in @('docker-compose.yml','Start-InHuis.ps1','Stop-InHuis.ps1','Uninstall-InHuis.ps1','README.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $packageRoot $name)
  }
  New-Item -ItemType Directory -Path (Join-Path $packageRoot 'data') | Out-Null
  $init = Join-Path $repoRoot 'docker\postgresql\init-roles.sh'
  $destination = Join-Path $packageRoot 'init-roles.sh'
  Copy-Item -LiteralPath $init -Destination $destination
  $manifest = "commit=$commit`ncreated=$((Get-Date).ToUniversalTime().ToString('o'))`nexternal_scanner=excluded`n"
  Set-Content -LiteralPath (Join-Path $packageRoot 'BUILD-MANIFEST.txt') -Value $manifest -Encoding UTF8
  Compress-Archive -Path $packageRoot -DestinationPath $zipPath -CompressionLevel Optimal
  Write-Host "Package created: $zipPath"
} catch {
  Write-Warning "Packaging aborted: $($_.Exception.Message)"
  throw
}
