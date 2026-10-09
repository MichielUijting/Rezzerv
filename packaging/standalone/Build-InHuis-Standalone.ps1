$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$release = Join-Path $root 'release'
New-Item -ItemType Directory -Path $release -Force | Out-Null
$log = Join-Path $release 'build.log'
Start-Transcript -Path $log -Force | Out-Null
try {
  Write-Host 'InHuis Standalone - Windows EXE bouw'
  if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is vereist.' }
  foreach ($cmd in @('git','npm','py')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Benodigd op BOUW-pc: $cmd" }
  }
  & py -3.11 -c 'import sys; print(sys.version)'
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 x64 ontbreekt op de bouw-pc.' }
  $pyhome = (& py -3.11 -c 'import sys; print(sys.base_prefix)').Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Python-basisinstallatie niet gevonden.' }
  $postgresCandidates = @()
  if ($env:INHUIS_POSTGRES_HOME) { $postgresCandidates += $env:INHUIS_POSTGRES_HOME }
  $postgresCandidates += @(Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object FullName)
  $postgresHome = $postgresCandidates | Where-Object { Test-Path (Join-Path $_ 'bin\initdb.exe') } | Select-Object -First 1
  if (-not $postgresHome) { throw 'Windows PostgreSQL serverbinaries ontbreken. Installeer op BOUW-pc PostgreSQL 17 of stel INHUIS_POSTGRES_HOME in.' }
  if (-not (Test-Path (Join-Path $postgresHome 'share'))) { throw 'PostgreSQL share-directory ontbreekt.' }
  $source = Join-Path $root 'portable-runtime'
  if (Test-Path $source) { throw 'portable-runtime bestaat al: om onverwacht overschrijven te vermijden gestopt. Verplaats deze map eerst.' }
  New-Item -ItemType Directory -Path $source -Force | Out-Null
  try {
    $pydest = Join-Path $source 'python'
    Copy-Item -LiteralPath $pyhome -Destination $pydest -Recurse
    Copy-Item -LiteralPath $postgresHome -Destination (Join-Path $source 'postgres') -Recurse
    $python = Join-Path $pydest 'python.exe'
    if (-not (Test-Path $python)) { throw 'Kopie van Python is ongeldig.' }
    # Install required backend dependencies in the copied runtime, not in the system Python.
    & $python -m pip install --disable-pip-version-check -r (Join-Path $root 'backend\requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Backend-afhankelijkheden kunnen niet worden gebundeld (mogelijk OCR/Paddle Windows wheel). Zie build.log.' }
    & $python -m pip install --disable-pip-version-check 'opencv-python-headless<5' 'paddlepaddle==3.2.0' 'pyinstaller>=6,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Paddle/OpenCV/PyInstaller Windows-bundeling mislukt. Zie build.log.' }
    $builder = Join-Path $PSScriptRoot 'Build-Windows-Portable.ps1'
    & $builder -RuntimeSource $source -OutputDirectory $release
    if ($LASTEXITCODE -ne 0) { throw 'ZIP-bouw mislukt.' }
    $pkg = Join-Path $release 'InHuis-Standalone'
    Push-Location $PSScriptRoot
    try {
      & $python -m PyInstaller --noconfirm --clean --onefile --name InHuis --distpath $pkg --workpath (Join-Path $release 'pyinstaller-work') --specpath (Join-Path $release 'pyinstaller-spec') (Join-Path $PSScriptRoot 'exe_entry.py')
      if ($LASTEXITCODE -ne 0) { throw 'InHuis.exe bundelen mislukt.' }
    } finally { Pop-Location }
    # Old ZIP predates EXE; regenerate once all package components exist.
    $zip = Join-Path $release 'InHuis-Standalone.zip'
    Remove-Item -LiteralPath $zip -Force
    Compress-Archive -LiteralPath $pkg -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "EXE en ZIP gemaakt: $zip"
    Write-Warning 'NIET AAN TESTERS STUREN totdat start/database/bonnen/uninstall op schone Windows machine zijn geslaagd.'
  } finally {
    Write-Host "Bouwruntime aanwezig voor diagnose: $source"
  }
} catch {
  Write-Error $_
  exit 1
} finally {
  Stop-Transcript | Out-Null
}
