param(
  [string]$RuntimeSource = "",
  [string]$OutputDirectory = ""
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $root "release" }
if (-not $RuntimeSource) { $RuntimeSource = Join-Path $root "portable-runtime" }
$python = Join-Path $RuntimeSource "python\python.exe"
$postgres = Join-Path $RuntimeSource "postgres\bin\postgres.exe"
$initdb = Join-Path $RuntimeSource "postgres\bin\initdb.exe"
$pgctl = Join-Path $RuntimeSource "postgres\bin\pg_ctl.exe"
foreach ($required in @($python,$postgres,$initdb,$pgctl)) {
  if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
    throw "Portable runtime onvolledig: $required. Geen automatische download of systeeminstallatie."
  }
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm is alleen op de BOUWcomputer nodig voor de frontend build."
}
$package = Join-Path $OutputDirectory "InHuis-Standalone"
$zip = Join-Path $OutputDirectory "InHuis-Standalone.zip"
if ((Test-Path -LiteralPath $package) -or (Test-Path -LiteralPath $zip)) {
  throw "Bestaande output wordt niet overschreven: $package / $zip"
}
# Verify installed Python environment before bundling; OCR native dependencies need separate smoke validation.
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw "De meegeleverde Python-omgeving bevat dependencyconflicten." }
& $python -c "import uvicorn, psycopg, fastapi, alembic, cv2, paddleocr"
if ($LASTEXITCODE -ne 0) { throw "De meegeleverde Python-omgeving mist noodzakelijke backend- of OCR-modules." }
Push-Location (Join-Path $root "frontend")
try {
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci mislukt." }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "Frontend build mislukt." }
} finally { Pop-Location }
New-Item -ItemType Directory -Path $package -Force | Out-Null
try {
  Copy-Item -LiteralPath $RuntimeSource -Destination (Join-Path $package "runtime") -Recurse
  Copy-Item -LiteralPath (Join-Path $root "backend") -Destination (Join-Path $package "backend") -Recurse
  Copy-Item -LiteralPath (Join-Path $root "frontend\dist") -Destination (Join-Path $package "www") -Recurse
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "portable_start.py") -Destination $package
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "portable_server.py") -Destination $package
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Portable-Start.cmd") -Destination (Join-Path $package "Start InHuis.cmd")
  Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Portable-Uninstall.cmd") -Destination (Join-Path $package "Uninstall InHuis.cmd")
  $commit = (git -C $root rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0) { throw "Git-commit niet gevonden." }
  Set-Content -LiteralPath (Join-Path $package "VERSION.txt") -Value $commit -Encoding ascii
  # Python virtualenvs and back-end development directories must not be shipped.
  foreach ($name in @(".venv", "__pycache__", "tests")) {
    $unwanted = Join-Path (Join-Path $package "backend") $name
    if (Test-Path -LiteralPath $unwanted) { Remove-Item -LiteralPath $unwanted -Recurse -Force }
  }
  New-Item -ItemType Directory -Path (Join-Path $package "data") | Out-Null
  Compress-Archive -Path $package -DestinationPath $zip -CompressionLevel Optimal
  Write-Host "Concept-ZIP gemaakt: $zip"
  Write-Warning "NIET DISTRIBUEREN: vereiste schone Windows-machine test, OCR-/native DLL-controle en uninstall-check."
} catch { throw }
