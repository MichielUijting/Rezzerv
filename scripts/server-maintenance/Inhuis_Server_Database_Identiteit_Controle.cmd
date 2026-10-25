@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
set "INHUIS_OWN_SCRIPT=%~f0"
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:INHUIS_OWN_SCRIPT); $m='# INHUIS_POWERSHELL_START'; $i=$s.LastIndexOf($m); if($i -lt 0){exit 2}; & ([scriptblock]::Create($s.Substring($i+$m.Length)))"
set "INHUIS_RC=%ERRORLEVEL%"
CLS
echo ============================================================
echo INHUIS - DATABASE-IDENTITEIT CONTROLEREN
echo ============================================================
if not "%INHUIS_RC%"=="0" (
  echo VEILIG GESTOPT: niet alle identiteitscontroles geslaagd.
) else (
  echo Alleen-lezen diagnose uitgevoerd. Dit is GEEN herstart-GO.
)
echo.
echo Rapport: %USERPROFILE%\Downloads\Inhuis_Server_Database_Identiteit_Resultaat.txt
echo Deel alleen dit TXT-bestand; geen configuratie of wachtwoorden.
echo Geen container, database, instelling of onderhoudsstatus gewijzigd.
echo.
pause
exit /b %INHUIS_RC%

# INHUIS_POWERSHELL_START
$ErrorActionPreference = 'Stop'
$reportDir = Join-Path $env:USERPROFILE 'Downloads'
if (-not (Test-Path -LiteralPath $reportDir -PathType Container)) { $reportDir = $env:TEMP }
$report = Join-Path $reportDir 'Inhuis_Server_Database_Identiteit_Resultaat.txt'
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('INHUIS - DATABASE-IDENTITEIT - ALLEEN LEZEN')
$lines.Add('Tijd: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
$lines.Add('Geen databasewijziging, Docker-start/stop, herstel of herstart uitgevoerd.')
$lines.Add('')
$ok = $false

try {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) { throw 'DOCKER_CLI_ONTBREEKT' }
    $ids = @(& docker.exe ps -aq 2>$null)
    if ($LASTEXITCODE -ne 0 -or $ids.Count -eq 0) { throw 'DOCKER_NIET_BEREIKBAAR_OF_LEEG' }
    $raw = & docker.exe inspect @ids 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'DOCKER_INSPECT_MISLUKT' }
    # Windows PowerShell 5.1 may emit the JSON array as ONE pipeline object.
    # Enumerate it explicitly to avoid selecting all containers as one backend.
    $parsed = ConvertFrom-Json -InputObject ($raw -join "`n")
    $containers = @()
    foreach ($item in $parsed) { $containers += $item }
    if ($containers.Count -ne $ids.Count) { throw 'DOCKER_INVENTARIS_AANTAL_AFWIJKEND' }
    $targetName = '/inhuis-1296-hersteltest-backend-1'
    $targets = @($containers | Where-Object { $_.Name -eq $targetName })
    if ($targets.Count -ne 1 -or $targets[0].State.Running -ne $true) { throw 'BEKENDE_BACKEND_NIET_UNIEK_OF_NIET_ACTIEF' }
    $backend = $targets[0]
    $lines.Add('Geselecteerde backend (eerder door PO als Inhuis-route bevestigd): ' + $targetName)
    $lines.Add('Backend image-ID: ' + $backend.Image)
    $lines.Add('Backend Compose-project: ' + $backend.Config.Labels.'com.docker.compose.project')
    $lines.Add('Backend herstartbeleid: ' + $backend.HostConfig.RestartPolicy.Name)

    # Python runs inside the already running backend; SQL uses its real runtime
    # DATABASE_URL, but neither URL nor credentials are printed or copied out.
    $probe = @'
import json, os, sys
try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    url = os.environ.get('DATABASE_URL')
    if not url:
        raise RuntimeError('NO_RUNTIME_DATABASE_URL')
    # Match the application's canonical psycopg 3 driver selection. A plain
    # postgresql:// URL otherwise makes SQLAlchemy look for absent psycopg2.
    parsed = make_url(url)
    if parsed.drivername == 'postgresql':
        parsed = parsed.set(drivername='postgresql+psycopg')
    if parsed.get_backend_name() != 'postgresql':
        raise RuntimeError('NOT_POSTGRESQL')
    engine = create_engine(parsed, connect_args={'connect_timeout': 5})
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION READ ONLY'))
        result = connection.execute(text('''
            SELECT current_database() AS database_name,
                   (SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,
                   inet_server_addr()::text AS server_ip,
                   inet_server_port() AS server_port,
                   pg_postmaster_start_time()::text AS database_boot,
                   current_setting('server_version') AS postgres_version
        ''')).mappings().one()
        revisions = [row[0] for row in connection.execute(text('SELECT version_num FROM alembic_version ORDER BY version_num'))]
        if not revisions:
            raise RuntimeError('NO_SCHEMA_REVISION')
        print('INHUIS_EVIDENCE=' + json.dumps(dict(result, revisions=revisions), sort_keys=True))
    engine.dispose()
except Exception as exc:
    # Only the exception class, never a connection URL or message with secrets.
    print('INHUIS_PROBE_FAILED=' + type(exc).__name__)
    sys.exit(3)
'@
    $output = @($probe | & docker.exe exec -i ($targetName.TrimStart('/')) python - 2>$null)
    if ($LASTEXITCODE -ne 0) {
        $failure = @($output | Where-Object { $_ -like 'INHUIS_PROBE_FAILED=*' } | Select-Object -First 1)
        if ($failure.Count -eq 1) { throw ('BACKEND_READONLY_SQL_MISLUKT_' + $failure[0].Substring('INHUIS_PROBE_FAILED='.Length)) }
        throw 'BACKEND_PYTHON_NIET_UITVOERBAAR_OF_GEEN_DIAGNOSE'
    }
    $evidenceLine = @($output | Where-Object { $_ -like 'INHUIS_EVIDENCE=*' })
    if ($evidenceLine.Count -ne 1) { throw 'DATABASE_EVIDENCE_ONTBREEKT' }
    $db = $evidenceLine[0].Substring('INHUIS_EVIDENCE='.Length) | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace($db.server_ip) -or [string]::IsNullOrWhiteSpace($db.database_name)) { throw 'DATABASE_IDENTITEIT_ONVOLLEDIG' }
    $lines.Add('Aangesloten database: ' + $db.database_name)
    $lines.Add('Database OID: ' + $db.database_oid)
    $lines.Add('PostgreSQL-adres/poort: ' + $db.server_ip + ':' + $db.server_port)
    $lines.Add('Databaseproces gestart: ' + $db.database_boot)
    $lines.Add('PostgreSQL-versie: ' + $db.postgres_version)
    $lines.Add('Alembic-schema: ' + (@($db.revisions) -join ','))

    # Match the actual server socket to running container interfaces, not a name.
    $matches = @()
    foreach ($container in $containers) {
        if ($container.State.Running -ne $true) { continue }
        $addresses = @($container.NetworkSettings.Networks.PSObject.Properties | ForEach-Object { $_.Value.IPAddress; $_.Value.GlobalIPv6Address })
        if ($addresses -contains [string]$db.server_ip) { $matches += $container }
    }
    if ($matches.Count -ne 1) { throw 'DATABASE_CONTAINER_NIET_UNIEK_GEIDENTIFICEERD' }
    $databaseContainer = $matches[0]
    $mounts = @($databaseContainer.Mounts | Where-Object { $_.Type -eq 'volume' -and $_.Destination -eq '/var/lib/postgresql/data' })
    if ($mounts.Count -ne 1 -or [string]::IsNullOrWhiteSpace($mounts[0].Name)) { throw 'DATABASE_VOLUME_ONBEKEND' }
    $lines.Add('Geidentificeerde databasecontainer: ' + $databaseContainer.Name)
    $lines.Add('Databasecontainer image-ID: ' + $databaseContainer.Image)
    $lines.Add('Geidentificeerd PostgreSQL-volume: ' + $mounts[0].Name)
    $lines.Add('Database Compose-project: ' + $databaseContainer.Config.Labels.'com.docker.compose.project')

    $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like 'Inhuis-Onderhoud*' })
    if ($tasks.Count -eq 0) {
        $lines.Add('Onderhoudsagent-taak: niet gevonden')
    } else {
        foreach ($task in $tasks) { $lines.Add('Onderhoudsagent-taak: ' + $task.TaskName + ' ; toestand=' + $task.State) }
    }
    $lines.Add('')
    $lines.Add('LET OP: dit is alleen socket/volume/schema-identificatie.')
    $lines.Add('Onderhoudsagent-handtekening, backupherstel, recente gebruikersdata en externe route zijn hiermee NIET bewezen.')
    $lines.Add('Geen toestemming voor reboot, databaseherstel of vrijgave van onderhoud.')
    $ok = $true
} catch {
    $lines.Add('VEILIG GESTOPT: ' + $_.Exception.Message)
    $lines.Add('Geen herstel of alternatieve database geselecteerd.')
}

$lines.Add('')
if ($ok) { $lines.Add('RESULTAAT: DIAGNOSE UITGEVOERD - GEEN HERSTART-GO') }
else { $lines.Add('RESULTAAT: VEILIG GESTOPT') }
try { [IO.File]::WriteAllLines($report, $lines, [Text.UTF8Encoding]::new($false)) }
catch { Write-Output 'Kon rapport niet schrijven.'; exit 2 }
if ($ok) { exit 0 }
exit 1
