@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
set "INHUIS_OWN_SCRIPT=%~f0"
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:INHUIS_OWN_SCRIPT); $m='# INHUIS_POWERSHELL_START'; $i=$s.LastIndexOf($m); if($i -lt 0){exit 2}; & ([scriptblock]::Create($s.Substring($i+$m.Length)))"
set "INHUIS_RC=%ERRORLEVEL%"
CLS
echo ============================================================
echo INHUIS - GEISOLEERDE SERVERHERSTARTPROEF
echo ============================================================
if not "%INHUIS_RC%"=="0" (
  echo VEILIG GESTOPT - zie het rapport voor de reden.
) else (
  echo Proef voltooid - de echte Inhuis-omgeving is niet gewijzigd.
)
echo.
echo Rapport: %USERPROFILE%\Downloads\Inhuis_Server_Geisoleerde_Herstartproef_Resultaat.txt
echo Deel alleen het TXT-rapport. Geen productieomschakeling uitgevoerd.
echo.
pause
exit /b %INHUIS_RC%

# INHUIS_POWERSHELL_START
$ErrorActionPreference = 'Stop'
$reportDirectory = Join-Path $env:USERPROFILE 'Downloads'
if (-not (Test-Path -LiteralPath $reportDirectory -PathType Container)) { $reportDirectory = $env:TEMP }
$report = Join-Path $reportDirectory 'Inhuis_Server_Geisoleerde_Herstartproef_Resultaat.txt'
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('INHUIS - GEISOLEERDE SERVERHERSTARTPROEF - ALLEEN SYNTHETISCHE DATA')
$lines.Add('Tijd: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
$lines.Add('Geen Windows-herstart, Inhuis-appstart, imagebuild, databaseherstel of productieomschakeling.')
$lines.Add('')
$project = ''
$composeFile = ''
$testContainerId = ''
$created = $false
$passed = $false

function Invoke-TestDocker([string[]]$Arguments) {
    $result = @(& docker.exe @Arguments 2>$null)
    if ($LASTEXITCODE -ne 0) { throw 'DOCKER_TESTOPDRACHT_MISLUKT' }
    return ($result -join "`n").Trim()
}
function Get-DockerIdentity([string]$Name) {
    $raw = Invoke-TestDocker @('inspect',$Name)
    $parsed = ConvertFrom-Json -InputObject $raw
    $objects = @()
    foreach ($item in $parsed) { $objects += $item }
    if ($objects.Count -ne 1) { throw 'DOCKER_IDENTITEIT_NIET_UNIEK' }
    return $objects[0]
}
function Invoke-TestCompose([string[]]$Arguments) {
    if (-not $project -or -not $composeFile) { throw 'TESTPROJECT_NIET_GESELECTEERD' }
    return Invoke-TestDocker (@('compose','--project-name',$project,'-f',$composeFile)+$Arguments)
}

try {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw 'DOCKER_ONTBREEKT' }
    [void](Invoke-TestDocker @('version','--format','{{.Server.Version}}'))
    [void](Invoke-TestDocker @('compose','version','--short'))
    $os = Get-CimInstance Win32_OperatingSystem
    if ([long]$os.FreePhysicalMemory -lt 900000) { throw 'MINDER_DAN_900_MIB_VRIJ_RAM' }
    [void](Invoke-TestDocker @('image','inspect','postgres:17-alpine','--format','{{.Id}}'))

    # Exact live identity from the most recent confirmed PO report. Read only.
    $backend = Get-DockerIdentity 'inhuis-1296-hersteltest-backend-1'
    $database = Get-DockerIdentity 'inhuis-1296-db-test'
    if (-not $backend.State.Running -or -not $database.State.Running) { throw 'BEVESTIGDE_LIVE_CONTAINERS_NIET_ACTIEF' }
    if ($backend.Image -cne 'sha256:3f5a12753683bf4afffd23068cddc04e0504b59a1c5839b9faaae0044d8b99eb') { throw 'LIVE_BACKEND_IMAGE_GEWIJZIGD' }
    if ($database.Image -cne 'sha256:79bd7c99e923138f136f8009d6bffa66e21e9d4fda5c0c561b00fc9c90cfe537') { throw 'LIVE_DATABASE_IMAGE_GEWIJZIGD' }
    $liveVolumes = @($database.Mounts | Where-Object { $_.Type -eq 'volume' -and $_.Destination -eq '/var/lib/postgresql/data' })
    if ($liveVolumes.Count -ne 1 -or $liveVolumes[0].Name -cne 'inhuis-hersteldata-936e1d62') { throw 'LIVE_DATABASE_VOLUME_GEWIJZIGD' }
    $lines.Add('Live backend/database/image/volume: exact gelijk aan eerder geverifieerde identiteit')
    $lines.Add('Actief databasevolume wordt NOOIT in de proef gebruikt.')

    $id = [guid]::NewGuid().ToString('N').Substring(0,12)
    $project = 'inhuis-repetitie-' + $id
    $directory = Join-Path (Join-Path $env:LOCALAPPDATA 'Inhuis\ServerRehearsal') $id
    [void](New-Item -ItemType Directory -Path $directory -Force)
    $composeFile = Join-Path $directory 'compose.yml'
    $yaml = @'
services:
  postgres:
    image: postgres:17-alpine
    pull_policy: never
    restart: unless-stopped
    network_mode: none
    mem_limit: 256m
    environment:
      POSTGRES_USER: inhuis_test
      POSTGRES_PASSWORD: inhuis_test_only_not_production
      POSTGRES_DB: inhuis_test
    command: ["postgres", "-c", "shared_buffers=32MB", "-c", "max_connections=20"]
    volumes:
      - rehearsal_data:/var/lib/postgresql/data
volumes:
  rehearsal_data:
'@
    [IO.File]::WriteAllText($composeFile,$yaml,[Text.UTF8Encoding]::new($false))
    [void](Invoke-TestCompose @('config','--quiet'))
    $lines.Add('Tijdelijk project: ' + $project)
    $lines.Add('Testconfiguratie: zonder hostpoorten of extern netwerk, zonder broncodebuild, met eigen Docker-volume')

    $created = $true
    [void](Invoke-TestCompose @('up','-d','--no-build','--pull','never'))
    $testContainerId = Invoke-TestCompose @('ps','-q','postgres')
    if ($testContainerId -notmatch '^[a-f0-9]{64}$') { throw 'TESTCONTAINER_ID_ONGELDIG' }
    $testContainer = Get-DockerIdentity $testContainerId
    if ($testContainer.Config.Labels.'com.docker.compose.project' -cne $project -or $testContainer.Config.Labels.'com.docker.compose.service' -cne 'postgres') { throw 'TESTCONTAINER_LABELS_ONJUIST' }
    $testVolumes = @($testContainer.Mounts | Where-Object { $_.Type -eq 'volume' -and $_.Destination -eq '/var/lib/postgresql/data' })
    if ($testVolumes.Count -ne 1 -or $testVolumes[0].Name -eq $liveVolumes[0].Name -or $testVolumes[0].Name -notlike ($project+'_*')) { throw 'TESTVOLUME_NIET_GEISOLEERD' }
    $lines.Add('Testvolume: ' + $testVolumes[0].Name)

    $ready = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        & docker.exe exec $testContainerId pg_isready -U inhuis_test -d inhuis_test 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'TESTDATABASE_NIET_GEREED' }

    $sql = "CREATE TABLE inhuis_rehearsal (marker text PRIMARY KEY); INSERT INTO inhuis_rehearsal VALUES ('$id');"
    [void](Invoke-TestDocker @('exec',$testContainerId,'psql','-X','-v','ON_ERROR_STOP=1','-U','inhuis_test','-d','inhuis_test','-c',$sql))
    $before = Invoke-TestDocker @('exec',$testContainerId,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','inhuis_test','-d','inhuis_test','-c','SELECT marker FROM inhuis_rehearsal')
    if ($before -cne $id) { throw 'TESTGEGEVENS_NIET_GESCHREVEN' }

    [void](Invoke-TestCompose @('stop','postgres'))
    [void](Invoke-TestCompose @('start','postgres'))
    $ready = $false
    for ($attempt=0; $attempt -lt 40; $attempt++) {
        & docker.exe exec $testContainerId pg_isready -U inhuis_test -d inhuis_test 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { $ready=$true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'TESTDATABASE_NA_HERSTART_NIET_GEREED' }
    $after = Invoke-TestDocker @('exec',$testContainerId,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','inhuis_test','-d','inhuis_test','-c','SELECT marker FROM inhuis_rehearsal')
    if ($after -cne $id) { throw 'TESTGEGEVENS_NA_HERSTART_VERSCHILLEN' }
    $lines.Add('Synthetische gegevens na Compose stop/start: IDENTIEK')
    $passed = $true
} catch {
    $lines.Add('VEILIG GESTOPT: ' + $_.Exception.Message)
} finally {
    if ($created -and -not $testContainerId -and $project -and $composeFile) {
        try { $testContainerId = Invoke-TestCompose @('ps','-aq','postgres') } catch { }
    }
    if ($created -and $testContainerId -match '^[a-f0-9]{64}$') {
        try {
            $current = Get-DockerIdentity $testContainerId
            if ($current.Config.Labels.'com.docker.compose.project' -ceq $project -and $current.Config.Labels.'com.docker.compose.service' -ceq 'postgres') {
                [void](Invoke-TestCompose @('stop','postgres'))
                $lines.Add('Eigen testcontainer na de proef gestopt om geheugen vrij te maken.')
            } else { $lines.Add('WAARSCHUWING: testcontainer-identiteit afwijkend; niets gestopt.') }
        } catch { $lines.Add('WAARSCHUWING: testcontainer mogelijk nog actief; geen bredere opruiming uitgevoerd.') }
    }
    if ($created) { $lines.Add('Testcontainer en testvolume blijven ter inspectie bestaan; GEEN volumes verwijderd.') }
    $lines.Add('Live Inhuis-containers en live databasevolume zijn niet gestopt, gewijzigd of aangekoppeld.')
    $lines.Add('Dit bewijst alleen geisoleerde PostgreSQL-persistentie; geen applicatie-, scanner-, agent- of Windows-rebootbewijs.')
    $lines.Add('')
    if ($passed) { $lines.Add('RESULTAAT: GEISOLEERDE DATABASEHERSTARTPROEF GESLAAGD - GEEN PRODUCTIE-GO') }
    else { $lines.Add('RESULTAAT: VEILIG GESTOPT') }
    try { [IO.File]::WriteAllLines($report,$lines,[Text.UTF8Encoding]::new($false)) }
    catch { Write-Output 'Kon rapport niet schrijven.'; exit 2 }
}
if ($passed) { exit 0 }
exit 1
