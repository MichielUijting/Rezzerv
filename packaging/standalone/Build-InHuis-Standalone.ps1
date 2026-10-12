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
  & py -3.12 -c 'import sys; print(sys.version)'
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 ontbreekt op de bouw-pc.' }
  $pyhome = (& py -3.12 -c 'import sys; print(sys.base_prefix)').Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Python-basisinstallatie niet gevonden.' }
  # Find a downloaded official Windows binaries archive without installing a service.
  $archive = Join-Path $env:USERPROFILE 'Downloads\postgresql-18.6-5-windows-x64-binaries.zip'
  if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
    throw "PostgreSQL archive ontbreekt: $archive"
  }
  $pyhome = (& py -3.12 -c 'import sys; print(sys.base_prefix)').Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 niet gevonden.' }
  if ($pyhome -match 'WindowsApps|Microsoft\\WindowsApps') {
    throw 'Microsoft Store Python is niet veilig overdraagbaar door simpel kopieren. Gebruik eerst een afzonderlijke officiele Windows Python 3.12 installatie op de bouw-pc; de bestaande Store-installatie blijft ongewijzigd.'
  }
  $extractRoot = Join-Path $release 'postgresql-extracted'
  if (Test-Path -LiteralPath $extractRoot) {
    throw "Tijdelijke extractiemap bestaat al; handmatige controle vereist: $extractRoot"
  }
  New-Item -ItemType Directory -Path $extractRoot | Out-Null
  Write-Host "PostgreSQL ZIP uitpakken: $archive"
  Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot
  $initdbFiles = @(Get-ChildItem -LiteralPath $extractRoot -Filter initdb.exe -File -Recurse)
  $valid = @($initdbFiles | Where-Object {
    (Test-Path (Join-Path $_.DirectoryName 'postgres.exe')) -and
    (Test-Path (Join-Path $_.DirectoryName 'pg_ctl.exe')) -and
    (Test-Path (Join-Path (Split-Path $_.DirectoryName -Parent) 'share'))
  })
  if ($valid.Count -ne 1) { throw "Geen eenduidige PostgreSQL runtime gevonden in archief; kandidaten: $($valid.Count)" }
  $postgresHome = Split-Path $valid[0].DirectoryName -Parent
  Write-Host "PostgreSQL runtime gevonden: $postgresHome"
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
