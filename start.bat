@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "REPO_DIR=%CD%"
set "TEMP_DIR=%TEMP%\Rezzerv-start-sync"
set "GIT_BRANCH="
set "GIT_HEAD_SHA="

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"
set "BACKEND_PORT=8001"
set "BACKEND_HEALTH_URL=http://localhost:%BACKEND_PORT%/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
set "DOCKER_DESKTOP_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"

echo ========================================
echo        Rezzerv Startup Routine
echo Projectmap: %CD%
echo Version: %REZZERV_VERSION%
echo ========================================
echo Modus: persistente normale start ^(runtime vanuit projectmap^)
echo Gebruik hard-reset.bat alleen voor een expliciete schone reset.

echo.
echo === Rezzerv Git Runtime Sync Start ===
echo.

call :ValidateGitRepository || exit /b 1
call :PrepareTempDir || exit /b 1
call :CaptureGitState || exit /b 1
call :FetchAndFastForward || exit /b 1
call :MirrorTrackedFilesToTemp || exit /b 1
call :ApplyTempToRepo || exit /b 1
call :CleanupTempDir >nul 2>&1

if exist "validate-version-sync.bat" (
  call validate-version-sync.bat
  if %errorlevel% neq 0 (
    echo [ERROR] Versiesync-check gefaald. Start wordt afgebroken.
    pause
    exit /b 1
  )
) else (
  echo [WARN] validate-version-sync.bat niet gevonden. Doorgaan zonder versiesync-check.
)

echo Valideren van projectstructuur...
if not exist "docker-compose.yml" goto :project_error
if not exist "backend" goto :project_error
if not exist "frontend" goto :project_error
if not exist "backend\data" (
  echo [WARN] backend\data ontbrak en wordt opnieuw aangemaakt.
  mkdir "backend\data" >nul 2>&1
)
if not exist "backend\data" (
  echo [ERROR] backend\data ontbreekt en kon niet worden aangemaakt.
  pause
  exit /b 1
)

echo Controleren op verboden lokale databasebestanden...
if exist "rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: rezzerv.db
  echo Verwijder of verplaats dit bestand eerst om meerdere runtime-bronnen te voorkomen.
  pause
  exit /b 1
)
if exist "backend\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: backend\rezzerv.db
  echo Verwijder of verplaats dit bestand eerst om meerdere runtime-bronnen te voorkomen.
  pause
  exit /b 1
)

call :SanitizeRepoRuntimeArtifacts || exit /b 1

echo Controleren of compose mount naar vaste runtime-locatie wijst...
findstr /I /C:"./backend/data:/app/data" "docker-compose.yml" >nul
if errorlevel 1 (
  echo [ERROR] docker-compose.yml mount niet conform runtime-regel.
  echo Verwacht: ./backend/data:/app/data
  pause
  exit /b 1
)

echo Checking Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker is not installed. Please install Docker Desktop.
  pause
  exit /b 1
)

call :EnsureDockerRunning || exit /b 1

echo Validating docker-compose.yml...
docker compose config >nul 2>&1
if %errorlevel% neq 0 (
  echo docker-compose.yml is invalid. See errors above.
  docker compose config
  pause
  exit /b 1
)

echo Sanitizing previous Rezzerv runtime...
echo [1/8] Stopping existing compose stack and removing orphans...
docker compose down --remove-orphans >nul 2>&1
docker compose rm -f -s -v >nul 2>&1

echo [1b/8] Removing legacy parallel Rezzerv stacks if present...
call :CleanupLegacyRezzervStacks || exit /b 1

echo [2/8] Checking active frontend port for leftover listeners...
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1

echo [2b/8] Checking active backend port for leftover listeners...
call :CleanupPortIfRezzerv %BACKEND_PORT% || exit /b 1

echo [2c/8] Releasing Docker-held frontend/backend ports after compose cleanup...
call :EnsurePortReleased %FRONTEND_PORT% || exit /b 1
call :EnsurePortReleased %BACKEND_PORT% || exit /b 1

echo [3/8] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning || exit /b 1

echo [4/8] Building updated images from projectmap...
docker compose build --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build failed.
  pause
  exit /b 1
)

echo [5/8] Starting containers without deleting project database...
docker compose up -d --remove-orphans --force-recreate
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  docker compose ps -a
  docker compose logs --tail 120
  pause
  exit /b 1
)

echo [6/8] Waiting for backend health...
call :WaitForBackendHealth || exit /b 1

echo [6b/8] Verifying backend reports the fixed runtime database...
call :VerifyRuntimeDatabase || exit /b 1

echo [7/8] Verifying active frontend port %FRONTEND_PORT%...
call :WaitForFrontend %FRONTEND_URL% || exit /b 1
call :VerifyFrontendPort
if %errorlevel% neq 0 (
  echo [ERROR] Frontend port verification failed.
  pause
  exit /b 1
)

echo [8/8] Opening frontend in browser...
start "" "%FRONTEND_URL%"

echo Starting Cloudflare Quick Tunnel in a separate window...
call :StartCloudflareTunnel

echo Startup complete.
exit /b 0

:ValidateGitRepository
if not exist "%REPO_DIR%\.git" (
  echo [ERROR] Geen geldige git repository in %REPO_DIR%
  pause
  exit /b 1
)
git --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Git is niet beschikbaar op deze computer.
  pause
  exit /b 1
)
exit /b 0

:PrepareTempDir
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%" >nul 2>&1
if not exist "%TEMP_DIR%" (
  echo [ERROR] Tijdelijke sync-map kon niet worden aangemaakt: %TEMP_DIR%
  pause
  exit /b 1
)
exit /b 0

:CaptureGitState
for /f "delims=" %%b in ('git branch --show-current') do set "GIT_BRANCH=%%b"
if "%GIT_BRANCH%"=="" (
  echo [ERROR] Huidige git branch kon niet worden bepaald.
  pause
  exit /b 1
)
for /f "delims=" %%h in ('git rev-parse HEAD 2^>nul') do set "GIT_HEAD_SHA=%%h"
echo Actieve branch: %GIT_BRANCH%
echo Lokale HEAD voor sync: %GIT_HEAD_SHA%
exit /b 0

:FetchAndFastForward
echo Git fetch uitvoeren...
git fetch --all --tags --prune
if %errorlevel% neq 0 (
  echo [ERROR] git fetch is mislukt.
  pause
  exit /b 1
)

echo Git pull uitvoeren op branch %GIT_BRANCH%...
git pull --ff-only
if %errorlevel% neq 0 (
  echo [ERROR] git pull --ff-only is mislukt. Los lokale branchproblemen eerst op.
  pause
  exit /b 1
)

for /f "delims=" %%h in ('git rev-parse HEAD 2^>nul') do set "GIT_HEAD_SHA=%%h"
echo Lokale HEAD na sync: %GIT_HEAD_SHA%
exit /b 0

:MirrorTrackedFilesToTemp
echo Repository-inhoud spiegelen naar tijdelijke map...
git archive --format=tar %GIT_HEAD_SHA% -o "%TEMP_DIR%\repo.tar"
if %errorlevel% neq 0 (
  echo [ERROR] git archive is mislukt.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "tar -xf '%TEMP_DIR%\repo.tar' -C '%TEMP_DIR%'"
if %errorlevel% neq 0 (
  echo [ERROR] Tijdelijke repository-spiegel kon niet worden uitgepakt.
  pause
  exit /b 1
)
del /q "%TEMP_DIR%\repo.tar" >nul 2>&1
if not exist "%TEMP_DIR%\docker-compose.yml" (
  echo [ERROR] Tijdelijke repository-spiegel is ongeldig ^(docker-compose.yml ontbreekt^).
  pause
  exit /b 1
)
exit /b 0

:ApplyTempToRepo
echo Bestanden kopieren naar repo ^(zonder .git, zonder runtime-data^)...
robocopy "%TEMP_DIR%" "%REPO_DIR%" /E /NFL /NDL /NJH /NJS /XD ".git" "backend\data" "frontend\node_modules" "backend\.venv" "Music"
set "ROBOCODE=%ERRORLEVEL%"
if %ROBOCODE% GEQ 8 (
  echo [ERROR] Robocopy sync naar repo is mislukt. Exitcode: %ROBOCODE%
  pause
  exit /b 1
)
exit /b 0

:CleanupTempDir
if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
exit /b 0

:project_error
echo Required project files/folders not found in current folder.
pause
exit /b 1

:SanitizeRepoRuntimeArtifacts
echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" del /f /q "%%F" >nul 2>&1
  )
)

echo Opschonen van release-documenten en runtime-caches...
for %%f in (
  "Rezzerv-Validatierapport_v*.txt"
  "Rezzerv-PO-testinstructie_v*.txt"
  "Rezzerv-Packaging-Manifest_v*.txt"
  "VALIDATIERAPPORT_v*.txt"
  "PO-TESTINSTRUCTIE_v*.txt"
  "Opleveringsmanifest_v*.txt"
  "RELEASE-GATE-COMPLIANCE_v*.txt"
  "BUILD-CHECK-v*.txt"
) do (
  del /q "%cd%\%%~f" 2>nul
)

if exist "%cd%\frontend\dist" rmdir /s /q "%cd%\frontend\dist"
if exist "%cd%\frontend\node_modules\.vite" rmdir /s /q "%cd%\frontend\node_modules\.vite"
if exist "%cd%\frontend\.vite" rmdir /s /q "%cd%\frontend\.vite"

for /r "%cd%" %%f in (*.pyc) do del /q "%%f" 2>nul
for /d /r "%cd%" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul

exit /b 0

:WaitForBackendHealth
set /a BACKEND_HEALTH_ATTEMPTS=0
:wait_backend_health
set /a BACKEND_HEALTH_ATTEMPTS+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %BACKEND_HEALTH_ATTEMPTS% GEQ 40 (
  echo [ERROR] Backend healthcheck werd niet op tijd groen.
  docker compose logs backend --tail 120
  pause
  exit /b 1
)
timeout /t 2 >nul
goto wait_backend_health

:VerifyRuntimeDatabase
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 3 } catch { Write-Host '[ERROR] Runtime healthcheck niet leesbaar.'; exit 31 };" ^
  "$db = [string]$r.database;" ^
  "if (-not $db) { Write-Host '[ERROR] Backend health geeft geen actief databasepad terug.'; exit 32 };" ^
  "if ($db -ne '/app/data/rezzerv.db') { Write-Host ('[ERROR] Backend gebruikt onverwachte runtime database: ' + $db); exit 33 };" ^
  "if ($r.PSObject.Properties.Name -contains 'database_valid') { if (-not [bool]$r.database_valid) { Write-Host '[ERROR] Backend markeert database_valid als false.'; exit 34 } };" ^
  "Write-Host ('    Runtime database bevestigd: ' + $db); exit 0"
if %errorlevel% neq 0 (
  echo [ERROR] Runtime database-validatie gefaald.
  pause
  exit /b 1
)
exit /b 0

:WaitForFrontend
set "TARGET_FRONTEND_URL=%~1"
set /a FRONTEND_WAIT_ATTEMPTS=0
:wait_frontend_ready
set /a FRONTEND_WAIT_ATTEMPTS+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%TARGET_FRONTEND_URL%/version.json' -UseBasicParsing -TimeoutSec 3; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %FRONTEND_WAIT_ATTEMPTS% GEQ 40 (
  echo [ERROR] Frontend werd niet op tijd bereikbaar op %TARGET_FRONTEND_URL%.
  docker compose logs frontend --tail 120
  pause
  exit /b 1
)
timeout /t 2 >nul
goto wait_frontend_ready

:EnsureDockerRunning
echo Checking if Docker engine is running...
docker info >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if not exist "%DOCKER_DESKTOP_EXE%" (
  echo [ERROR] Docker Desktop executable niet gevonden op %DOCKER_DESKTOP_EXE%
  pause
  exit /b 1
)
echo Docker engine not running.
echo Attempting to start Docker Desktop...
start "" "%DOCKER_DESKTOP_EXE%"
echo Waiting for Docker engine...
set /a DOCKER_WAIT_ATTEMPTS=0
:waitdocker
set /a DOCKER_WAIT_ATTEMPTS+=1
timeout /t 5 >nul
docker info >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %DOCKER_WAIT_ATTEMPTS% GEQ 24 (
  echo [ERROR] Docker engine kwam niet op tijd beschikbaar.
  pause
  exit /b 1
)
goto waitdocker

:CleanupLegacyRezzervStacks
set "LEGACY_FOUND="
for %%N in (rezzerv-dev-frontend-1 rezzerv-dev-backend-1 rezzerv-dev-db-1) do (
  docker ps -a --format "{{.Names}}" | findstr /I /X "%%N" >nul
  if !errorlevel! equ 0 (
    set "LEGACY_FOUND=1"
    echo     Removing explicitly known legacy container %%N ...
    docker stop %%N >nul 2>&1
    docker rm -f %%N >nul 2>&1
  )
)
for /f "usebackq delims=" %%N in (`docker ps -a --format "{{.Names}}"`) do (
  set "CONTAINER_NAME=%%N"
  set "IS_LEGACY="
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv-dev-" set "IS_LEGACY=1"
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv_dev_" set "IS_LEGACY=1"
  if defined IS_LEGACY (
    set "LEGACY_FOUND=1"
    echo     Removing legacy container !CONTAINER_NAME! ...
    docker stop !CONTAINER_NAME! >nul 2>&1
    docker rm -f !CONTAINER_NAME! >nul 2>&1
  )
)
if not defined LEGACY_FOUND echo     No legacy parallel Rezzerv stack detected.
exit /b 0

:CleanupPortIfRezzerv
set "TARGET_PORT=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%TARGET_PORT%;" ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if (-not $listener) { Write-Host ('    Port ' + $port + ' is free.'); exit 0 }" ^
  "$owningPid = $listener.OwningProcess;" ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue;" ^
  "$name = if ($proc) { $proc.Name } else { '' };" ^
  "$cmd = if ($proc) { [string]$proc.CommandLine } else { '' };" ^
  "$sig = ($name + ' ' + $cmd).ToLowerInvariant();" ^
  "$isDockerName = $name -match '(?i)^(docker|docker desktop|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$';" ^
  "$isDockerCmd = $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby';" ^
  "$isDocker = $isDockerName -or $isDockerCmd;" ^
  "$isWslRelayName = $name -match '(?i)^wslrelay\\.exe$';" ^
  "$isWslRelayCmd = $cmd.ToLowerInvariant() -match '--vm-id|wslrelay';" ^
  "$isWslRuntime = $isWslRelayName -or $isWslRelayCmd;" ^
  "$isRezzerv = $sig -match 'rezzerv';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\\.exe$|(?i)^powershell\\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|vite');" ^
  "if ($isDocker) { Write-Host ('[INFO] Port ' + $port + ' is occupied by Docker process PID ' + $owningPid + ' (' + $name + '). Action: postpone to Docker port-release step'); exit 0 }" ^
  "if ($isWslRuntime) { Write-Host ('[INFO] Port ' + $port + ' is occupied by WSL/runtime process PID ' + $owningPid + ' (' + $name + '). Action: postpone to Docker port-release step'); exit 0 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="12" echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  if not "%errorlevel%"=="12" echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
  pause
  exit /b 1
)
exit /b 0

:EnsurePortReleased
set "TARGET_PORT=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%TARGET_PORT%;" ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if (-not $listener) { Write-Host ('    Port ' + $port + ' is free after cleanup.'); exit 0 }" ^
  "$owningPid = $listener.OwningProcess;" ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue;" ^
  "$name = if ($proc) { $proc.Name } else { '' };" ^
  "$cmd = if ($proc) { [string]$proc.CommandLine } else { '' };" ^
  "$isDockerName = $name -match '(?i)^(docker|docker desktop|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$';" ^
  "$isDockerCmd = $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby';" ^
  "$isDocker = $isDockerName -or $isDockerCmd;" ^
  "$isWslRelayName = $name -match '(?i)^wslrelay\\.exe$';" ^
  "$isWslRelayCmd = $cmd.ToLowerInvariant() -match '--vm-id|wslrelay';" ^
  "$isWslRuntime = $isWslRelayName -or $isWslRelayCmd;" ^
  "if ($isDocker -or $isWslRuntime) { exit 99 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' bleef bezet door onbekend proces PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
if "%errorlevel%"=="0" exit /b 0
if "%errorlevel%"=="99" (
  echo [WARN] Port %TARGET_PORT% wordt nog door Docker/WSL vastgehouden. Docker Desktop wordt eenmalig herstart.
  call :RestartDockerDesktopForPortRelease %TARGET_PORT% || exit /b 1
  exit /b 0
)
echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
pause
exit /b 1

:RestartDockerDesktopForPortRelease
set "TARGET_PORT=%~1"
echo     Closing Docker Desktop so port %TARGET_PORT% can be released...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-Process -Name 'Docker Desktop','com.docker.backend' -ErrorAction SilentlyContinue; foreach ($p in $procs) { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {} }; try { wsl --shutdown | Out-Null } catch {}" >nul 2>&1
call :WaitForPortFree %TARGET_PORT% 24 5 || exit /b 1
call :EnsureDockerRunning || exit /b 1
call :WaitForPortFree %TARGET_PORT% 12 2 || exit /b 1
exit /b 0

:WaitForPortFree
set "TARGET_PORT=%~1"
set "MAX_ATTEMPTS=%~2"
set "SLEEP_SECONDS=%~3"
set /a PORT_WAIT_ATTEMPTS=0
:wait_port_free_loop
set /a PORT_WAIT_ATTEMPTS+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -State Listen -LocalPort %TARGET_PORT% -ErrorAction SilentlyContinue | Select-Object -First 1) { exit 1 } else { exit 0 }" >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %PORT_WAIT_ATTEMPTS% GEQ %MAX_ATTEMPTS% (
  echo [ERROR] Port %TARGET_PORT% bleef bezet na cleanup/herstart.
  netstat -aon | findstr :%TARGET_PORT%
  pause
  exit /b 1
)
timeout /t %SLEEP_SECONDS% >nul
goto wait_port_free_loop

:CleanupRezzervCloudflared
powershell -NoProfile -ExecutionPolicy Bypass -Command "$targetUrl='http://localhost:%FRONTEND_PORT%'; $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue ^| Where-Object { $_.Name -eq 'cloudflared.exe' }; foreach ($proc in $procs) { $cmd=[string]$proc.CommandLine; if ($cmd -and $cmd.ToLowerInvariant().Contains($targetUrl.ToLowerInvariant())) { try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop; Write-Host ('    Stopped previous Rezzerv Cloudflare tunnel PID ' + $proc.ProcessId + '.'); } catch {} } }"
exit /b 0

:StartCloudflareTunnel
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
  echo [WARN] cloudflared not found. Skipping Cloudflare tunnel startup.
  exit /b 0
)
call :CleanupRezzervCloudflared
if not exist "%cd%\start-cloudflare-tunnel.bat" (
  echo [WARN] start-cloudflare-tunnel.bat not found. Skipping Cloudflare tunnel startup.
  exit /b 0
)
start "Rezzerv Cloudflare Tunnel" cmd /k start-cloudflare-tunnel.bat "%FRONTEND_URL%"
echo     Cloudflare tunnel window opened separately.
exit /b 0

:VerifyFrontendPort
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$currentVersion='%REZZERV_VERSION%';" ^
  "$primaryUrl='http://localhost:%FRONTEND_PORT%';" ^
  "function GetVersion([string]$base, [ref]$raw) { $headers=@{'Cache-Control'='no-cache, no-store, must-revalidate'; 'Pragma'='no-cache'}; $raw.Value=''; try { $u = $base + '/version.json?cb=' + [guid]::NewGuid().ToString('N'); $resp = Invoke-WebRequest -Uri $u -Headers $headers -UseBasicParsing -TimeoutSec 3; $raw.Value = [string]$resp.Content; try { $v = $raw.Value | ConvertFrom-Json -ErrorAction Stop; if ($v.version) { return [string]$v.version } } catch {} } catch {}; try { $u = $base + '/?cb=' + [guid]::NewGuid().ToString('N'); $resp = Invoke-WebRequest -Uri $u -Headers $headers -UseBasicParsing -TimeoutSec 3; $content=[string]$resp.Content; if (-not $raw.Value) { $raw.Value = $content }; $m=[regex]::Match($content,'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)'); if ($m.Success) { return $m.Groups[1].Value }; if ($content -match 'Rezzerv') { return 'UI_CONFIRMED_NO_VERSION' } } catch {}; return '' }" ^
  "$primaryBody = ''; $primaryVersion = GetVersion $primaryUrl ([ref]$primaryBody);" ^
  "if (-not $primaryVersion) { exit 21 }" ^
  "if ($primaryVersion -ne 'UI_CONFIRMED_NO_VERSION' -and $primaryVersion -ne $currentVersion) { $flat = (($primaryBody -replace '\s+',' ').Trim()); $sample = $flat.Substring(0, [Math]::Min($flat.Length, 220)); Write-Host ('[ERROR] Active frontend on port %FRONTEND_PORT% serves version ' + $primaryVersion + ' instead of ' + $currentVersion + '. Response sample: ' + $sample); exit 23 }" ^
  "if ($primaryVersion -eq 'UI_CONFIRMED_NO_VERSION') { Write-Host ('[INFO] Active frontend on port %FRONTEND_PORT% serves Rezzerv UI, but no machine-detectable version string was found. Action: allow'); exit 0 }" ^
  "Write-Host ('    Active frontend verified on port %FRONTEND_PORT% with version ' + $primaryVersion + '.'); exit 0"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="21" echo [ERROR] Expected frontend port %FRONTEND_PORT% is not reachable.
  exit /b 1
)
exit /b 0
