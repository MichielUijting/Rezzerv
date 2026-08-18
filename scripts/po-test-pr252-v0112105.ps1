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

# Productcode die technisch wordt geaccepteerd. Latere commits mogen uitsluitend
# PO-testondersteuning/documentatie bevatten en worden hieronder expliciet bewaakt.
$ProductSha = 'd57110208093f410253cc1772077ac06ec9ac6fd'
$ExpectedVersion = 'Rezzerv-MVP-v01.12.105'
$ExpectedShortVersion = 'v01.12.105'
$PrNumber = '252'
$ProjectName = 'rezzerv-pr252-v0112105-po'
$FixtureName = 'PO-test Herkenning v01.12.105'
$FixtureSource = 'po_local_fixture'
$FixtureCode = 'po:v01.12.105:external-recognition'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogDir = Join-Path $env:TEMP 'Rezzerv-PO-tests'
$Log = Join-Path $LogDir "Rezzerv-PO-test-v0112105-$Stamp.log"
$Worktree = Join-Path $env:TEMP "rezzerv-v0112105-$Stamp"
$WorktreeAdded = $false
$IsolatedStarted = $false
$StoppedContainers = @()
$FunctionalNoGo = $false
$TechnicalFailure = ''
$OldVersionEnv = $env:REZZERV_VERSION
$OldCommitEnv = $env:REZZERV_COMMIT

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
  finally {
    if ($Cwd) { Pop-Location }
  }
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

function Wait-BackendHealth([int]$Seconds = 210) {
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

function Wait-Frontend([int]$Seconds = 90) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      $version = Invoke-RestMethod -Uri 'http://localhost:5174/version.json' -TimeoutSec 5
      if ($version.version) { return $version }
    }
    catch { }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  throw "Frontend werd niet bereikbaar binnen $Seconds seconden."
}

function Containers-OnPort([int]$Port) {
  $ids = @(& docker ps --filter "publish=$Port" --format '{{.ID}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "Docker kon poort $Port niet inspecteren." }
  return @($ids | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
}

if ($SelfTest) {
  if ($ProductSha -notmatch '^[0-9a-f]{40}$') { throw 'SELFTEST: product-SHA ongeldig.' }
  if ($ExpectedVersion -ne 'Rezzerv-MVP-v01.12.105') { throw 'SELFTEST: versie ongeldig.' }
  if ($ExpectedShortVersion -ne 'v01.12.105') { throw 'SELFTEST: korte versie ongeldig.' }
  if ($PrNumber -ne '252') { throw 'SELFTEST: PR-nummer ongeldig.' }
  if ($ProjectName -match '^rezzerv$') { throw 'SELFTEST: Docker-project moet geisoleerd zijn.' }
  if ($FixtureName -notmatch 'v01\.12\.105') { throw 'SELFTEST: fixtureversie ongeldig.' }
  Write-Output 'PO_TEST_V0112105_SELFTEST_GREEN'
  exit 0
}

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType File -Path $Log -Force | Out-Null
Log 'Release Protocol v1.1 - Compliance Check:'
Log "Versie: $ExpectedVersion"
Log "Bewezen productcommit: $ProductSha"
Log "PR: #$PrNumber"
Log "SSOT: $Repo"
Log 'Testmodel: detached worktree + kopie van de vaste runtime-database; live database wordt niet gewijzigd.'

try {
  foreach ($cmd in @('git', 'docker')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
      throw "Programma ontbreekt: $cmd"
    }
  }
  if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) {
    throw "Git-repository niet gevonden. Gecontroleerd: $($RepoCandidates -join ' | ')"
  }

  & docker info *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is niet beschikbaar.' }

  $originalHead = Capture 'git' @('-C', $Repo, 'rev-parse', 'HEAD')
  $originalStatus = Capture 'git' @('-C', $Repo, 'status', '--porcelain=v1', '--untracked-files=all')
  Log "Oorspronkelijke HEAD: $originalHead"
  if ($originalStatus) {
    Log 'Lokale wijzigingen zijn aanwezig; ze worden niet gewijzigd en niet als productbron gebruikt.'
  }

  Run 'git' @('-C', $Repo, 'fetch', '--no-tags', 'origin', "refs/pull/$PrNumber/head") | Out-Null
  $prHead = Capture 'git' @('-C', $Repo, 'rev-parse', 'FETCH_HEAD')
  Log "Actuele PR-head: $prHead"

  & git -C $Repo merge-base --is-ancestor $ProductSha $prHead *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Bewezen productcommit $ProductSha is geen voorouder meer van PR #$PrNumber."
  }

  $allowedAfterProduct = @(
    'backend/tests/po_external_recognition_fixture.py',
    'scripts/po-test-pr252-v0112105.ps1',
    'scripts/START-PO-TEST-PR252.cmd',
    '.github/workflows/pr252-po-test-script-windows.yml'
  )
  $changedAfterProduct = Capture 'git' @('-C', $Repo, 'diff', '--name-only', "$ProductSha..$prHead")
  if ($changedAfterProduct) {
    $unexpected = @(
      $changedAfterProduct -split "`n" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -and ($_ -notin $allowedAfterProduct) }
    )
    if ($unexpected.Count -gt 0) {
      throw "Onverwachte productwijzigingen na bewezen commit: $($unexpected -join ', ')"
    }
  }

  # Werk op de actuele PR-head zodat de testfixture beschikbaar is. De diffguard
  # hierboven bewijst dat alle productbestanden nog exact die van $ProductSha zijn.
  Run 'git' @('-C', $Repo, 'worktree', 'add', '--detach', $Worktree, $prHead) | Out-Null
  $WorktreeAdded = $true

  $actualVersion = (Get-Content -LiteralPath (Join-Path $Worktree 'VERSION.txt') -Raw).Trim()
  if ($actualVersion -ne $ExpectedVersion) {
    throw "VERSION.txt=$actualVersion; verwacht $ExpectedVersion."
  }

  $liveDataDir = Join-Path $Repo 'backend\data'
  $liveDb = Join-Path $liveDataDir 'rezzerv.db'
  if (-not (Test-Path -LiteralPath $liveDb)) {
    throw "Vaste runtime-database ontbreekt: $liveDb"
  }

  $StoppedContainers = @(
    (Containers-OnPort 8011) +
    (Containers-OnPort 5174) |
      Select-Object -Unique
  )
  if ($StoppedContainers.Count -gt 0) {
    Log "Bestaande Rezzerv-containers tijdelijk stoppen: $($StoppedContainers -join ', ')"
    Run 'docker' (@('stop') + $StoppedContainers) | Out-Null
  }

  $testDataDir = Join-Path $Worktree 'backend\data'
  New-Item -ItemType Directory -Path $testDataDir -Force | Out-Null
  $testDb = Join-Path $testDataDir 'rezzerv.db'
  Copy-Item -LiteralPath $liveDb -Destination $testDb -Force
  foreach ($suffix in @('-wal', '-shm')) {
    $source = "$liveDb$suffix"
    if (Test-Path -LiteralPath $source) {
      Copy-Item -LiteralPath $source -Destination "$testDb$suffix" -Force
    }
  }
  Log "Geisoleerde testdatabase: $testDb"

  $env:REZZERV_VERSION = $ExpectedVersion
  $env:REZZERV_COMMIT = $ProductSha
  $compose = Join-Path $Worktree 'docker-compose.yml'

  Run 'docker' @('compose', '-p', $ProjectName, '-f', $compose, 'build', '--no-cache') $Worktree | Out-Null
  Run 'docker' @('compose', '-p', $ProjectName, '-f', $compose, 'up', '-d') $Worktree | Out-Null
  $IsolatedStarted = $true

  $health = Wait-BackendHealth 210
  Log "Backend-health: $($health.status)"
  $frontendVersion = Wait-Frontend 90
  if ($frontendVersion.version -ne $ExpectedVersion) {
    throw "Frontend toont $($frontendVersion.version); verwacht $ExpectedVersion."
  }
  Log "Frontendversie: $($frontendVersion.version)"

  $openApi = Invoke-RestMethod -Uri 'http://localhost:8011/openapi.json' -TimeoutSec 20
  $confirmRoute = '/api/external-databases/candidates/confirm-external'
  if (-not ($openApi.paths.PSObject.Properties.Name -contains $confirmRoute)) {
    throw "Nieuwe bevestigingsroute ontbreekt in OpenAPI: $confirmRoute"
  }
  Log 'OpenAPI bevestigingsroute = GREEN.'

  Run 'docker' @(
    'compose', '-p', $ProjectName, '-f', $compose,
    'exec', '-T', 'backend', 'sh', '-lc',
    'cd /app && PYTHONPATH=/app python tests/test_external_recognition_confirmation.py'
  ) $Worktree | Out-Null
  Log 'Backend herkenningscontract = GREEN.'

  $fixtureOutput = Capture 'docker' @(
    'compose', '-p', $ProjectName, '-f', $compose,
    'exec', '-T', 'backend', 'sh', '-lc',
    'cd /app && PYTHONPATH=/app python tests/po_external_recognition_fixture.py prepare'
  ) $Worktree
  if ($fixtureOutput -notmatch 'PO_EXTERNAL_RECOGNITION_FIXTURE_GREEN') {
    throw 'PO-testfixture kon niet aantoonbaar worden voorbereid.'
  }
  Log 'Deterministische PO-testfixture = GREEN.'

  Start-Process 'http://localhost:5174/externe-databases'
  Write-Host ''
  Write-Host '======================================================================'
  Write-Host 'TECHNISCHE PRECHECK = GREEN'
  Write-Host "Test nu functioneel: $ExpectedVersion"
  Write-Host 'De live Rezzerv-database blijft onaangeraakt; je test op een kopie.'
  Write-Host '======================================================================'
  Write-Host ''
  Write-Host 'PO-TESTSCRIPT'
  Write-Host '1. Log in met je normale Rezzerv-account als dat scherm verschijnt.'
  Write-Host '2. Open Externe databases en controleer rechtsonder versie v01.12.105.'
  Write-Host "3. Zoek in het blok 'Herkenning bevestigen' de rij met Herkend artikel: $FixtureName."
  Write-Host "   Verwacht: status 'Herkenning beschikbaar', bron '$FixtureSource' en code '$FixtureCode'."
  Write-Host '4. Dubbelklik die rij. De detailtabel Herkenningskandidaten opent.'
  Write-Host '   De PO-testkandidaat moet geselecteerd zijn en bron/code moeten gelijk blijven.'
  Write-Host "5. Klik exact op 'Bevestig herkenning'."
  Write-Host "   Verwacht direct feedback en status: 'Herkenning bevestigd'."
  Write-Host '6. Klik op Vernieuwen in hetzelfde blok.'
  Write-Host "   Verwacht: de rij blijft 'Herkenning bevestigd' en bron/code blijven zichtbaar."
  Write-Host "7. De rij mag NIET veranderen in 'Catalogus gekoppeld'."
  Write-Host '   Cataloguskoppeling blijft een aparte vervolgstap.'
  Write-Host '8. Open met F12 de browserconsole en controleer dat deze flow geen nieuwe errors geeft.'
  Write-Host ''

  $checks = @(
    "Externe databases opent en versielabel $ExpectedShortVersion is zichtbaar",
    "PO-testregel toont Herkenning beschikbaar met bron $FixtureSource en vaste winkel-/broncode",
    'Dubbelklik opent de herkenningskandidaten en de juiste kandidaat is selecteerbaar',
    'Bevestig herkenning geeft Herkenning bevestigd',
    'Na Vernieuwen blijft Herkenning bevestigd met dezelfde bron en code zichtbaar',
    'De bevestigde herkenning wordt niet als Catalogus gekoppeld getoond',
    'Geen nieuwe browserconsole-errors tijdens deze flow'
  )

  foreach ($check in $checks) {
    if (-not (Ask $check)) {
      $FunctionalNoGo = $true
      Log "PO NO-GO: $check"
    }
    else {
      Log "PO OK: $check"
    }
  }

  $verifyOutput = Capture 'docker' @(
    'compose', '-p', $ProjectName, '-f', $compose,
    'exec', '-T', 'backend', 'sh', '-lc',
    'cd /app && PYTHONPATH=/app python tests/po_external_recognition_fixture.py verify'
  ) $Worktree
  if ($verifyOutput -notmatch 'PO_EXTERNAL_RECOGNITION_VERIFY_GREEN') {
    throw 'Automatische invariantcontrole na de PO-test is niet groen.'
  }
  Log 'Automatische invariantcontrole: geen Catalogus-, Mijn artikel- of voorraad-eventmutatie = GREEN.'
}
catch {
  $TechnicalFailure = $_.Exception.Message
  Log "TECHNISCHE FOUT: $TechnicalFailure"
}
finally {
  if ($IsolatedStarted -and (Test-Path -LiteralPath $Worktree)) {
    try {
      $compose = Join-Path $Worktree 'docker-compose.yml'
      Run 'docker' @('compose', '-p', $ProjectName, '-f', $compose, 'down', '--volumes', '--remove-orphans') $Worktree | Out-Null
    }
    catch {
      Log "Cleanup-waarschuwing Docker: $($_.Exception.Message)"
    }
  }

  if ($WorktreeAdded) {
    try {
      Run 'git' @('-C', $Repo, 'worktree', 'remove', '--force', $Worktree) | Out-Null
    }
    catch {
      Log "Cleanup-waarschuwing worktree: $($_.Exception.Message)"
    }
  }

  if ($StoppedContainers.Count -gt 0) {
    try {
      Run 'docker' (@('start') + $StoppedContainers) | Out-Null
    }
    catch {
      Log "Cleanup-waarschuwing bestaande containers: $($_.Exception.Message)"
    }
  }

  if ($null -eq $OldVersionEnv) {
    Remove-Item Env:REZZERV_VERSION -ErrorAction SilentlyContinue
  }
  else {
    $env:REZZERV_VERSION = $OldVersionEnv
  }

  if ($null -eq $OldCommitEnv) {
    Remove-Item Env:REZZERV_COMMIT -ErrorAction SilentlyContinue
  }
  else {
    $env:REZZERV_COMMIT = $OldCommitEnv
  }

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
