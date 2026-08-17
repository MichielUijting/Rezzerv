param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoCandidates = @(
  'C:\Users\Gebruiker\Rezzerv_Github',
  'C:\Users\Gebruiker\OneDrive\Scans\Documenten\GitHub\Rezzerv'
)
$Repo = $RepoCandidates[0]
foreach ($candidate in $RepoCandidates) {
  if (Test-Path -LiteralPath (Join-Path $candidate '.git')) {
    $Repo = $candidate
    break
  }
}
$ProductSha = '9a1944cc760d4d7355b48f8106f620ab0ee351ed'
$ExpectedVersion = 'Rezzerv-MVP-v01.12.97'
$ProjectName = 'rezzerv-pr251-v011297-po'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogDir = Join-Path $env:TEMP 'Rezzerv-PO-tests'
$Log = Join-Path $LogDir "Rezzerv-PO-test-v011297-$Stamp.log"
$Worktree = Join-Path $env:TEMP "rezzerv-v011297-$Stamp"
$WorktreeAdded = $false
$IsolatedStarted = $false
$StoppedContainers = @()
$FunctionalNoGo = $false
$TechnicalFailure = ''
$OldVersionEnv = $env:REZZERV_VERSION

function Log([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
  Write-Host $line
  Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}

function Run([string]$Exe, [string[]]$Arguments, [string]$Cwd = '') {
  if ($Cwd) { Push-Location $Cwd }
  try {
    Log ("> {0} {1}" -f $Exe, ($Arguments -join ' '))
    $out = @(& $Exe @Arguments 2>&1)
    $rc = $LASTEXITCODE
    foreach ($line in $out) { Log ([string]$line) }
    if ($rc -ne 0) { throw "Exitcode ${rc}: $Exe $($Arguments -join ' ')" }
    return $out
  }
  finally { if ($Cwd) { Pop-Location } }
}

function Capture([string]$Exe, [string[]]$Arguments, [string]$Cwd = '') {
  $out = Run $Exe $Arguments $Cwd
  return (($out | ForEach-Object { [string]$_ }) -join "`n").Trim()
}

function Ask([string]$Question) {
  while ($true) {
    $answer = (Read-Host "$Question [J/N]").Trim().ToUpperInvariant()
    if ($answer -eq 'J') { return $true }
    if ($answer -eq 'N') { return $false }
    Write-Host 'Antwoord met J of N.'
  }
}

function Wait-BackendHealth([int]$Seconds = 150) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      $health = Invoke-RestMethod -Uri 'http://localhost:8011/api/health' -TimeoutSec 5
      if ($health.status -eq 'ok') { return $health }
    }
    catch { }
    Start-Sleep -Seconds 3
  } while ((Get-Date) -lt $deadline)
  throw "Backend-health werd niet groen binnen $Seconds seconden."
}

function Containers-OnPort([int]$Port) {
  $ids = @(& docker ps --filter "publish=$Port" --format '{{.ID}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "Docker kon poort $Port niet inspecteren." }
  return @($ids | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
}

if ($SelfTest) {
  if ($ProductSha -notmatch '^[0-9a-f]{40}$') { throw 'SELFTEST: product-SHA ongeldig.' }
  if ($ExpectedVersion -ne 'Rezzerv-MVP-v01.12.97') { throw 'SELFTEST: versie ongeldig.' }
  if ($Repo -notin $RepoCandidates) { throw 'SELFTEST: SSOT-pad ongeldig.' }
  if ($ProjectName -match '^rezzerv$') { throw 'SELFTEST: Docker-project moet geisoleerd zijn.' }
  Write-Output 'PO_TEST_V011297_SELFTEST_GREEN'
  exit 0
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType File -Path $Log -Force | Out-Null
Log 'Release Protocol v1.1 - Compliance Check:'
Log "Versie: $ExpectedVersion"
Log "Bewezen productcommit: $ProductSha"
Log "SSOT: $Repo"
Log 'Testmodel: detached worktree + kopie van de vaste runtime-database; live database wordt niet gewijzigd.'

try {
  foreach ($cmd in @('git','docker')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Programma ontbreekt: $cmd" }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) {
    throw "Git-repository niet gevonden. Gecontroleerd: $($RepoCandidates -join ' | ')"
  }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is niet beschikbaar.' }

  $originalHead = Capture 'git' @('-C',$Repo,'rev-parse','HEAD')
  $originalStatus = Capture 'git' @('-C',$Repo,'status','--porcelain=v1','--untracked-files=all')
  Log "Oorspronkelijke HEAD: $originalHead"
  if ($originalStatus) { Log 'Lokale wijzigingen zijn aanwezig; ze worden niet gewijzigd en niet als buildbron gebruikt.' }

  Run 'git' @('-C',$Repo,'fetch','--no-tags','origin','refs/pull/251/head') | Out-Null
  $prHead = Capture 'git' @('-C',$Repo,'rev-parse','FETCH_HEAD')
  Log "Actuele PR-head: $prHead"
  & git -C $Repo merge-base --is-ancestor $ProductSha $prHead *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Bewezen productcommit is geen voorouder meer van PR #251.' }

  $allowedAfterProduct = @(
    'scripts/po-test-pr251-v011297.ps1',
    'scripts/START-PO-TEST-PR251.cmd',
    '.github/workflows/pr251-po-test-script-windows.yml',
    '.github/workflows/pr251-v011297-release-package.yml',
    'docs/quality/M2C2N-FINAL-REPORT.md'
  )
  $changedAfterProduct = Capture 'git' @('-C',$Repo,'diff','--name-only',"$ProductSha..$prHead")
  if ($changedAfterProduct) {
    $unexpected = @($changedAfterProduct -split "`n" | Where-Object { $_ -and ($_ -notin $allowedAfterProduct) })
    if ($unexpected.Count -gt 0) { throw "Onverwachte productwijzigingen na bewezen commit: $($unexpected -join ', ')" }
  }

  Run 'git' @('-C',$Repo,'worktree','add','--detach',$Worktree,$ProductSha) | Out-Null
  $WorktreeAdded = $true
  $actualVersion = (Get-Content -LiteralPath (Join-Path $Worktree 'VERSION.txt') -Raw).Trim()
  if ($actualVersion -ne $ExpectedVersion) { throw "VERSION.txt=$actualVersion; verwacht $ExpectedVersion." }

  $liveDataDir = Join-Path $Repo 'backend\data'
  $liveDb = Join-Path $liveDataDir 'rezzerv.db'
  if (-not (Test-Path -LiteralPath $liveDb)) { throw "Vaste runtime-database ontbreekt: $liveDb" }

  $StoppedContainers = @((Containers-OnPort 8011) + (Containers-OnPort 5174) | Select-Object -Unique)
  if ($StoppedContainers.Count -gt 0) {
    Log "Bestaande Rezzerv-containers tijdelijk stoppen: $($StoppedContainers -join ', ')"
    Run 'docker' (@('stop') + $StoppedContainers) | Out-Null
  }

  $testDataDir = Join-Path $Worktree 'backend\data'
  New-Item -ItemType Directory -Path $testDataDir -Force | Out-Null
  $testDb = Join-Path $testDataDir 'rezzerv.db'
  Copy-Item -LiteralPath $liveDb -Destination $testDb -Force
  foreach ($suffix in @('-wal','-shm')) {
    $source = "$liveDb$suffix"
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination "$testDb$suffix" -Force }
  }
  Log "Geisoleerde testdatabase: $testDb"

  $env:REZZERV_VERSION = $ExpectedVersion
  $compose = Join-Path $Worktree 'docker-compose.yml'
  Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'build','--no-cache') $Worktree | Out-Null
  Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'up','-d') $Worktree | Out-Null
  $IsolatedStarted = $true

  $health = Wait-BackendHealth 150
  Log "Backend-health: $($health.status)"
  $versionPayload = Invoke-RestMethod -Uri 'http://localhost:5174/version.json' -TimeoutSec 10
  if ($versionPayload.version -ne $ExpectedVersion) { throw "Frontend toont $($versionPayload.version); verwacht $ExpectedVersion." }
  Log "Frontendversie: $($versionPayload.version)"

  $backendChecks = @(
    'cd /app && PYTHONPATH=/app python tests/run_article_detail_mutation_contract.py',
    'cd /app && PYTHONPATH=/app python tests/test_article_detail_admin_gateway_contract.py',
    'cd /app && PYTHONPATH=/app python tests/test_article_detail_canonical_route_guard.py'
  )
  foreach ($check in $backendChecks) {
    Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'exec','-T','backend','sh','-lc',$check) $Worktree | Out-Null
  }
  Log 'Gerichte Artikeldetail contractchecks = GREEN.'

  Start-Process 'http://localhost:5174'
  Write-Host ''
  Write-Host '============================================================'
  Write-Host 'TECHNISCHE PRECHECK = GREEN'
  Write-Host "Test nu functioneel: $ExpectedVersion"
  Write-Host '============================================================'
  Write-Host ''
  Write-Host 'PO-TESTSCRIPT'
  Write-Host '1. Log in als Eigenaar/Admin en ga via Startpagina naar Voorraad.'
  Write-Host '2. Controleer rechtsonder versie v01.12.97.'
  Write-Host '3. Kies een voorraadartikel en open het detailscherm.'
  Write-Host '4. Overzicht > Artikel: wijzig Naam in dit huishouden in een herkenbare testnaam en sla op.'
  Write-Host '5. Ga terug naar Voorraad: dezelfde waarde moet in de kolom Voorraadartikel staan.'
  Write-Host '6. Open het artikel opnieuw. Loop de subtabs Artikel, Huishouden, Identiteit en Productdata langs.'
  Write-Host '   Per actieve subtab: precies een buitenframe, geen interne framekoppen en nergens + of - voor inklappen.'
  Write-Host '7. Open Analyse en loop Trends, Prijs, Prognose en Onderbouwing langs.'
  Write-Host '   Ook hier: een buitenframe per subtab, geen interne framekoppen en geen + of - bediening.'
  Write-Host '8. Controleer dat Voorraad, Locaties en Historie nog normaal openen.'
  Write-Host '9. Log in als Lid en open hetzelfde artikel: lezen moet werken; bewerken/corrigeren/verplaatsen moet geblokkeerd zijn.'
  Write-Host '10. Controleer browserconsole: geen nieuwe errors tijdens deze flow.'
  Write-Host ''

  $checks = @(
    'Eigenaar/Admin: Login -> Startpagina -> Voorraad werkt',
    'Versielabel v01.12.97 zichtbaar',
    'Naam in dit huishouden komt terug als Voorraadartikel in het Voorraadoverzicht',
    'Overzicht-subtabs hebben een frame en geen +/-, inklapbediening of interne framekoppen',
    'Analyse-subtabs hebben een frame en geen +/-, inklapbediening of interne framekoppen',
    'Voorraad/Locaties/Historie zijn ongewijzigd bruikbaar',
    'Lid kan alles lezen maar niets muteren in Artikeldetail',
    'Geen nieuwe browserconsole-errors'
  )
  foreach ($check in $checks) {
    if (-not (Ask $check)) {
      $FunctionalNoGo = $true
      Log "PO NO-GO: $check"
    }
    else { Log "PO OK: $check" }
  }
}
catch {
  $TechnicalFailure = $_.Exception.Message
  Log "TECHNISCHE FOUT: $TechnicalFailure"
}
finally {
  if ($IsolatedStarted -and (Test-Path -LiteralPath $Worktree)) {
    try {
      $compose = Join-Path $Worktree 'docker-compose.yml'
      Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'down','--volumes','--remove-orphans') $Worktree | Out-Null
    }
    catch { Log "Cleanup-waarschuwing Docker: $($_.Exception.Message)" }
  }
  if ($WorktreeAdded) {
    try { Run 'git' @('-C',$Repo,'worktree','remove','--force',$Worktree) | Out-Null }
    catch { Log "Cleanup-waarschuwing worktree: $($_.Exception.Message)" }
  }
  if ($StoppedContainers.Count -gt 0) {
    try { Run 'docker' (@('start') + $StoppedContainers) | Out-Null }
    catch { Log "Cleanup-waarschuwing bestaande containers: $($_.Exception.Message)" }
  }
  if ($null -eq $OldVersionEnv) { Remove-Item Env:REZZERV_VERSION -ErrorAction SilentlyContinue }
  else { $env:REZZERV_VERSION = $OldVersionEnv }
  Log 'Cleanup afgerond.'
  Log "Logbestand: $Log"
}

if ($TechnicalFailure) {
  Write-Host "TESTRESULTAAT: TECHNISCHE NO-GO - $TechnicalFailure"
  exit 1
}
if ($FunctionalNoGo) {
  Write-Host 'TESTRESULTAAT: FUNCTIONELE NO-GO'
  exit 2
}
Write-Host 'TESTRESULTAAT: PO-TEST GROEN'
exit 0
