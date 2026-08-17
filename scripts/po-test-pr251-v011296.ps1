param([switch]$SelfTest)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = 'C:\Users\Gebruiker\Rezzerv_Github'
$ProductSha = '51d20083012f3f094b7407c538741ef329e61d68'
$ExpectedVersion = 'Rezzerv-MVP-v01.12.96'
$ArticleId = '2c93edd7-c65a-46e8-8272-73611c9f5c3b'
$ProjectName = 'rezzerv-pr251-po'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($Desktop)) { $Desktop = $env:TEMP }
$Log = Join-Path $Desktop "Rezzerv-PO-test-PR251-$Stamp.log"
$Worktree = Join-Path $env:TEMP "rezzerv-pr251-$Stamp"
$OriginalContainers = @()
$OriginalHead = ''
$OriginalStatus = ''
$WorktreeAdded = $false
$IsolatedStarted = $false
$CleanupFailed = $false
$FunctionalNoGo = $false
$TechnicalFailure = ''
$OldVersionEnv = $env:REZZERV_VERSION

function Log([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $Message
  Write-Host $line
  Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}

function Run([string]$Exe, [string[]]$Args, [string]$Cwd = '') {
  if ($Cwd) { Push-Location $Cwd }
  try {
    Log ("> {0} {1}" -f $Exe, ($Args -join ' '))
    $out = @(& $Exe @Args 2>&1)
    $code = $LASTEXITCODE
    foreach ($line in $out) { Log ([string]$line) }
    if ($code -ne 0) { throw "Exitcode ${code}: $Exe $($Args -join ' ')" }
    return $out
  } finally { if ($Cwd) { Pop-Location } }
}

function Capture([string]$Exe, [string[]]$Args, [string]$Cwd = '') {
  if ($Cwd) { Push-Location $Cwd }
  try {
    $out = @(& $Exe @Args 2>&1)
    $code = $LASTEXITCODE
    if ($code -ne 0) {
      foreach ($line in $out) { Log ([string]$line) }
      throw "Exitcode ${code}: $Exe $($Args -join ' ')"
    }
    return (($out | ForEach-Object { [string]$_ }) -join "`n").Trim()
  } finally { if ($Cwd) { Pop-Location } }
}

function PortContainers([int]$Port) {
  $ids = @(& docker ps --filter "publish=$Port" --format '{{.ID}}' 2>$null)
  if ($LASTEXITCODE -ne 0) { throw "Docker kon poort $Port niet inspecteren." }
  return @($ids | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
}

function AssertService([string]$Id, [string]$Service) {
  $actual = (& docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' $Id 2>$null | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or $actual -ne $Service) {
    throw "Poort wordt gebruikt door onverwachte container $Id (service '$actual', verwacht '$Service')."
  }
}

function NormalizeHostPath([string]$PathValue) {
  $p = ([string]$PathValue).Trim()
  if ($p -match '^/host_mnt/([A-Za-z])/(.*)$') {
    $p = "$($Matches[1]):\$($Matches[2] -replace '/', '\')"
  } elseif ($p -match '^/run/desktop/mnt/host/([A-Za-z])/(.*)$') {
    $p = "$($Matches[1]):\$($Matches[2] -replace '/', '\')"
  }
  return ([System.IO.Path]::GetFullPath($p).Replace('/','\')).TrimEnd([char]'\').ToLowerInvariant()
}

function Ask([string]$Question) {
  while ($true) {
    $a = (Read-Host "$Question [J/N]").Trim().ToUpperInvariant()
    if ($a -eq 'J') { return $true }
    if ($a -eq 'N') { return $false }
    Write-Host 'Antwoord met J of N.'
  }
}

function WaitHealth([int]$Seconds = 120) {
  $until = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      $h = Invoke-RestMethod -Uri 'http://localhost:8011/api/health' -TimeoutSec 5
      if ($h.status -eq 'ok') { return $h }
    } catch { }
    Start-Sleep -Seconds 3
  } while ((Get-Date) -lt $until)
  throw "Backend-health werd niet groen binnen $Seconds seconden."
}

if ($SelfTest) {
  if ($ProductSha -notmatch '^[0-9a-f]{40}$') { throw 'SELFTEST: product-SHA ongeldig.' }
  if ($Repo -ne 'C:\Users\Gebruiker\Rezzerv_Github') { throw 'SELFTEST: SSOT-werkmap ongeldig.' }
  if ($ExpectedVersion -ne 'Rezzerv-MVP-v01.12.96') { throw 'SELFTEST: versie ongeldig.' }
  if ($ProjectName -in @('rezzerv','rezzerv_github')) { throw 'SELFTEST: project niet geisoleerd.' }
  if ((NormalizeHostPath 'C:/Users/Gebruiker/Rezzerv_Github') -ne (NormalizeHostPath $Repo)) { throw 'SELFTEST: padnormalisatie ongeldig.' }
  Write-Output 'PO_TEST_SCRIPT_SELFTEST_GREEN'
  exit 0
}

New-Item -ItemType File -Path $Log -Force | Out-Null
Log 'Release Protocol v1.1 - Compliance Check:'
Log "PR #251 - $ExpectedVersion"
Log "Bewezen productcommit: $ProductSha"
Log "SSOT-werkmap: $Repo"
Log 'Testmodel: detached worktree + geisoleerde kopie van rezzerv.db.'

try {
  if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) { throw "Rezzerv-repository niet gevonden: $Repo" }
  foreach ($cmd in @('git','docker')) { if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "Programma niet gevonden: $cmd" } }
  & docker info *> $null
  if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is niet beschikbaar.' }

  $OriginalHead = Capture 'git' @('-C',$Repo,'rev-parse','HEAD')
  $OriginalStatus = Capture 'git' @('-C',$Repo,'status','--porcelain=v1','--untracked-files=all')
  Log "Oorspronkelijke HEAD: $OriginalHead"
  if ($OriginalStatus) {
    Log 'Lokale wijzigingen gedetecteerd; deze worden niet als buildbron gebruikt en niet gewijzigd.'
    foreach ($line in ($OriginalStatus -split "`n")) { Log "  $line" }
  } else { Log 'Lokale werkmap is schoon.' }

  Run 'git' @('-C',$Repo,'fetch','--no-tags','origin','refs/pull/251/head') | Out-Null
  $PrHead = Capture 'git' @('-C',$Repo,'rev-parse','FETCH_HEAD')
  Log "Actuele PR-head: $PrHead"
  & git -C $Repo merge-base --is-ancestor $ProductSha $PrHead *> $null
  if ($LASTEXITCODE -ne 0) { throw 'De bewezen productcommit zit niet meer in de actuele PR-head.' }
  $afterProduct = Capture 'git' @('-C',$Repo,'diff','--name-only',"$ProductSha..$PrHead")
  if ($afterProduct) {
    $unexpected = @()
    foreach ($path in ($afterProduct -split "`n")) {
      if ($path -notmatch '^scripts/po-test-pr251-v011296\.ps1$' -and $path -notmatch '^\.github/workflows/pr251-po-test-script-windows\.yml$') { $unexpected += $path }
    }
    if ($unexpected.Count -gt 0) { throw "Nieuwe productwijzigingen na bewezen commit: $($unexpected -join ', ')" }
    Log 'Latere PR-wijzigingen zijn uitsluitend PO-testvalidatiebestanden.'
  }

  Run 'git' @('-C',$Repo,'worktree','add','--detach',$Worktree,$ProductSha) | Out-Null
  $WorktreeAdded = $true
  if ((Capture 'git' @('-C',$Worktree,'rev-parse','HEAD')) -ne $ProductSha) { throw 'Tijdelijke worktree staat op verkeerde commit.' }
  $version = (Get-Content -LiteralPath (Join-Path $Worktree 'VERSION.txt') -Raw).Trim()
  if ($version -ne $ExpectedVersion) { throw "VERSION.txt is '$version', verwacht '$ExpectedVersion'." }

  $ExpectedDataDir = Join-Path $Repo 'backend\data'
  $LiveDb = Join-Path $ExpectedDataDir 'rezzerv.db'
  if (-not (Test-Path -LiteralPath $LiveDb)) { throw "Vaste runtime-database niet gevonden: $LiveDb" }
  $back = @(PortContainers 8011); $front = @(PortContainers 5174)
  if ($back.Count -gt 1 -or $front.Count -gt 1) { throw 'Meer dan een container gebruikt een vaste Rezzerv-poort.' }
  foreach ($id in $back) { AssertService $id 'backend' }
  foreach ($id in $front) { AssertService $id 'frontend' }
  if ($back.Count -eq 1) {
    $mountedData = (& docker inspect --format '{{ range .Mounts }}{{ if eq .Destination "/app/data" }}{{ .Source }}{{ end }}{{ end }}' $back[0] 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mountedData)) { throw 'Draaiende backend heeft geen aantoonbare /app/data-bindmount.' }
    if ((NormalizeHostPath $mountedData) -ne (NormalizeHostPath $ExpectedDataDir)) {
      throw "Draaiende backend gebruikt onverwachte /app/data-bron: $mountedData"
    }
    Log "Runtime-databron bevestigd: $mountedData -> /app/data"
  } else {
    Log "Geen draaiende backend op 8011; SSOT-databron voor de geisoleerde test: $ExpectedDataDir"
  }
  $OriginalContainers = @($back + $front | Select-Object -Unique)
  if ($OriginalContainers.Count -gt 0) {
    Log "Bestaande Rezzerv-containers tijdelijk stoppen: $($OriginalContainers -join ', ')"
    Run 'docker' (@('stop') + $OriginalContainers) | Out-Null
  }

  $testData = Join-Path $Worktree 'backend\data'
  New-Item -ItemType Directory -Path $testData -Force | Out-Null
  $TestDb = Join-Path $testData 'rezzerv.db'
  Copy-Item -LiteralPath $LiveDb -Destination $TestDb -Force
  $LiveWal = "$LiveDb-wal"
  if (Test-Path -LiteralPath $LiveWal) { Copy-Item -LiteralPath $LiveWal -Destination "$TestDb-wal" -Force }
  if (-not (Test-Path -LiteralPath $TestDb)) { throw 'Testdatabase kon niet worden gemaakt.' }
  Log "Geisoleerde testdatabase: $TestDb"

  $env:REZZERV_VERSION = $ExpectedVersion
  $compose = Join-Path $Worktree 'docker-compose.yml'
  Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'build','--no-cache') $Worktree | Out-Null
  Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'up','-d') $Worktree | Out-Null
  $IsolatedStarted = $true

  $health = WaitHealth 120
  Log "Backend-health: $($health.status)"
  if (($health | ConvertTo-Json -Depth 6 -Compress) -notmatch 'rezzerv\.db') { throw 'Healthcheck bevestigt rezzerv.db niet.' }
  $v = Invoke-RestMethod -Uri 'http://localhost:5174/version.json' -TimeoutSec 10
  if ($v.version -ne $ExpectedVersion) { throw "Frontendversie is '$($v.version)', verwacht '$ExpectedVersion'." }
  Log "Frontendversie: $($v.version)"

  Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'exec','-T','backend','sh','-lc','cd /app && PYTHONPATH=/app python -m py_compile app/main.py app/services/server_session_service.py app/services/session_request_context.py tests/test_article_detail_mutation_contract.py') $Worktree | Out-Null
  $contract = Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'exec','-T','backend','sh','-lc','cd /app && PYTHONPATH=/app python tests/test_article_detail_mutation_contract.py') $Worktree
  if ((($contract | ForEach-Object { [string]$_ }) -join "`n") -notmatch 'ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN') { throw 'Artikeldetail-contractrunner gaf geen GREEN-marker.' }
  Log 'Gerichte backend/API-contractvalidatie = GREEN.'

  $fixtureCode = 'import sqlite3,sys; aid="{0}"; c=sqlite3.connect("/app/data/rezzerv.db"); a=c.execute("SELECT naam FROM household_articles WHERE id=? LIMIT 1",(aid,)).fetchone(); n=c.execute("SELECT COUNT(*) FROM inventory WHERE household_article_id=? AND COALESCE(status,?)=?",(aid,"active","active")).fetchone()[0]; print("ARTICLE_FIXTURE_GREEN:" + str(a[0]) + ":" + str(n) if a and int(n or 0)>=1 else "ARTICLE_FIXTURE_MISSING"); c.close(); sys.exit(0 if a and int(n or 0)>=1 else 2)' -f $ArticleId
  $fixture = Run 'docker' @('compose','-p',$ProjectName,'-f',$compose,'exec','-T','backend','python','-c',$fixtureCode) $Worktree
  if ((($fixture | ForEach-Object { [string]$_ }) -join "`n") -notmatch 'ARTICLE_FIXTURE_GREEN:') { throw 'Testartikel/actieve voorraadfixture ontbreekt.' }
  Log 'Testartikel en actieve voorraadregel = GREEN.'

  Write-Host ''; Write-Host '============================================================'
  Write-Host 'TECHNISCHE PRECHECK = GREEN'
  Write-Host "Versie: $ExpectedVersion"
  Write-Host "Productcommit: $ProductSha"
  Write-Host 'Lokale werkmap: niet gewijzigd en niet als buildbron gebruikt'
  Write-Host 'PO-testmutaties: uitsluitend op een geisoleerde kopie van rezzerv.db'
  Write-Host '============================================================'; Write-Host ''

  $url = "http://localhost:5174/voorraad/$ArticleId"
  Write-Host 'FUNCTIONELE PO-TEST - 7 Granen Ontbijt'
  Write-Host "Browser: $url"
  Write-Host 'Als login verschijnt: log normaal in als Eigenaar/Admin en open daarna dezelfde artikel-URL.'
  Write-Host 'Laat dit PowerShell-venster open totdat TESTRESULTAAT en Cleanup afgerond zijn getoond.'
  Start-Process $url

  Write-Host ''; Write-Host 'TEST 1 - Overzicht'
  Write-Host "In 'Artikelgegevens voor dit huishouden' is alleen 'Eigen naam' bewerkbaar. Categorie, merk, barcode en extern artikelnummer zijn daar geen tweede mutatiepad."
  if (-not (Ask 'Voldoet TEST 1?')) { $FunctionalNoGo=$true; throw 'FUNCTIONAL_NO_GO: TEST 1' }

  Write-Host ''; Write-Host 'TEST 2 - Eigen naam'
  Write-Host "Wijzig Eigen naam in 'PO TEST PR251', klik buiten het veld, wacht op opslagfeedback, ververs en controleer persistentie."
  if (-not (Ask 'Voldoet TEST 2?')) { $FunctionalNoGo=$true; throw 'FUNCTIONAL_NO_GO: TEST 2' }

  Write-Host ''; Write-Host 'TEST 3 - Instellingen voor dit huishouden'
  Write-Host "Controleer dat velden en Opslaan bruikbaar zijn. Zet Notities op 'PO TEST PR251', sla op, ververs en controleer persistentie."
  if (-not (Ask 'Voldoet TEST 3?')) { $FunctionalNoGo=$true; throw 'FUNCTIONAL_NO_GO: TEST 3' }

  Write-Host ''; Write-Host 'TEST 4 - Externe productkoppeling'
  Write-Host "Controleer dat 'Barcode invullen' zichtbaar en klikbaar is. Bestaat al een barcode, controleer dan de overschrijfwaarschuwing en kies NIET overschrijven. Sla geen nieuwe barcode op."
  if (-not (Ask 'Voldoet TEST 4?')) { $FunctionalNoGo=$true; throw 'FUNCTIONAL_NO_GO: TEST 4' }

  Write-Host ''; Write-Host 'TEST 5 - Automatisering'
  Write-Host "Controleer dat de automatiseringskeuze bruikbaar is. Kies een andere optie, wacht op 'Opgeslagen', ververs en controleer persistentie."
  if (-not (Ask 'Voldoet TEST 5?')) { $FunctionalNoGo=$true; throw 'FUNCTIONAL_NO_GO: TEST 5' }
  Log 'FUNCTIONELE PO-TEST = GO.'
}
catch {
  $m = $_.Exception.Message
  if ($FunctionalNoGo -or $m.StartsWith('FUNCTIONAL_NO_GO:')) { $FunctionalNoGo=$true; Log "FUNCTIONELE PO-TEST = NO-GO. $m" }
  else { $TechnicalFailure=$m; Log "TECHNISCHE PRECHECK/UITVOERING = NO-GO. $m" }
}
finally {
  Log 'Cleanup gestart.'
  try {
    if ($IsolatedStarted -and (Test-Path -LiteralPath (Join-Path $Worktree 'docker-compose.yml'))) {
      & docker compose -p $ProjectName -f (Join-Path $Worktree 'docker-compose.yml') down --volumes --remove-orphans 2>&1 | ForEach-Object { Log ([string]$_) }
      if ($LASTEXITCODE -ne 0) { throw 'Geisoleerde Dockeromgeving kon niet worden gestopt.' }
    }
  } catch { $CleanupFailed=$true; Log "CLEANUP-FOUT Docker: $($_.Exception.Message)" }
  try {
    if ($OriginalContainers.Count -gt 0) {
      & docker start @OriginalContainers 2>&1 | ForEach-Object { Log ([string]$_) }
      if ($LASTEXITCODE -ne 0) { throw 'Oorspronkelijke Rezzerv-containers konden niet worden herstart.' }
      Log 'Oorspronkelijke Rezzerv-containers zijn herstart.'
    }
  } catch { $CleanupFailed=$true; Log "CLEANUP-FOUT originele runtime: $($_.Exception.Message)" }
  try {
    if ($WorktreeAdded -and (Test-Path -LiteralPath $Worktree)) {
      & git -C $Repo worktree remove --force $Worktree 2>&1 | ForEach-Object { Log ([string]$_) }
      if ($LASTEXITCODE -ne 0) { throw 'Tijdelijke worktree kon niet worden verwijderd.' }
      & git -C $Repo worktree prune *> $null
    }
  } catch { $CleanupFailed=$true; Log "CLEANUP-FOUT worktree: $($_.Exception.Message)" }
  if ($null -eq $OldVersionEnv) { Remove-Item Env:REZZERV_VERSION -ErrorAction SilentlyContinue } else { $env:REZZERV_VERSION=$OldVersionEnv }
  try {
    if ($OriginalHead) {
      $headAfter=Capture 'git' @('-C',$Repo,'rev-parse','HEAD')
      $statusAfter=Capture 'git' @('-C',$Repo,'status','--porcelain=v1','--untracked-files=all')
      if ($headAfter -ne $OriginalHead) { throw 'Lokale HEAD veranderde onverwacht.' }
      if ($statusAfter -ne $OriginalStatus) { throw 'Lokale Git-status wijkt na de test af.' }
      Log 'Lokale Git HEAD en werkmapstatus zijn aantoonbaar ongewijzigd.'
    }
  } catch { $CleanupFailed=$true; Log "CLEANUP-FOUT Git-borging: $($_.Exception.Message)" }
  Log 'Cleanup afgerond.'
}

Write-Host ''; Write-Host '============================================================'
if ($CleanupFailed) { Write-Host 'TESTRESULTAAT = TECHNISCHE NO-GO (cleanup/herstel)'; Write-Host "Log: $Log"; Write-Host 'Geen handmatige Git- of databaseherstelacties uitvoeren.'; exit 30 }
if ($TechnicalFailure) { Write-Host 'TESTRESULTAAT = TECHNISCHE NO-GO'; Write-Host "Reden: $TechnicalFailure"; Write-Host "Log: $Log"; Write-Host 'De app-code is hiermee niet functioneel afgekeurd.'; exit 10 }
if ($FunctionalNoGo) { Write-Host 'TESTRESULTAAT = FUNCTIONELE NO-GO'; Write-Host "Log: $Log"; Write-Host 'De PO-testmutaties zijn alleen op de geisoleerde databasekopie uitgevoerd.'; exit 20 }
Write-Host 'TESTRESULTAAT = FUNCTIONELE GO'; Write-Host "Log: $Log"; Write-Host 'De PO-testmutaties zijn alleen op de geisoleerde databasekopie uitgevoerd.'; Write-Host '============================================================'; exit 0
