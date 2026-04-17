@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"
set "BACKEND_HEALTH_URL=http://localhost:8001/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

echo ========================================
echo        Rezzerv Startup Routine
echo Projectmap: %CD%
echo Version: %REZZERV_VERSION%
echo ========================================
echo Modus: persistente normale start ^(runtime vanuit projectmap^)
echo Gebruik hard-reset.bat alleen voor een expliciete schone reset.

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
  echo [ERROR] backend\data ontbreekt. Runtime database-structuur ongeldig.
  pause
  exit /b 1
)

echo Controleren op verboden lokale databasebestanden...
if exist "rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: rezzerv.db
  echo Verwijder dit bestand eerst om meerdere runtime-bronnen te voorkomen.
  pause
  exit /b 1
)
if exist "backend\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: backend\rezzerv.db
  echo Verwijder dit bestand eerst om meerdere runtime-bronnen te voorkomen.
  pause
  exit /b 1
)

echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" del /f /q "%%F" >nul 2>&1
  )
)

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
echo [1/7] Stopping existing compose stack and removing orphans...
docker compose down --remove-orphans >nul 2>&1

echo [1b/7] Removing legacy parallel Rezzerv stacks if present...
call :CleanupLegacyRezzervStacks || exit /b 1

echo [2/7] Checking active frontend port for leftover listeners...
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1

echo [3/7] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning || exit /b 1

echo [4/7] Building updated images from projectmap...
docker compose build --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build failed.
  pause
  exit /b 1
)

echo [5/7] Starting containers without deleting project database...
docker compose up -d --remove-orphans --force-recreate >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  docker compose logs --tail 80
  pause
  exit /b 1
)

echo [6/7] Waiting for backend health...
call :WaitForBackendHealth || exit /b 1

echo [6b/7] Verifying backend reports the fixed runtime database...
call :VerifyRuntimeDatabase || exit /b 1

echo [7/7] Verifying active frontend port %FRONTEND_PORT%...
call :WaitForFrontend %FRONTEND_URL% || exit /b 1
call :VerifyFrontendPort
if %errorlevel% neq 0 (
  echo [ERROR] Frontend port verification failed.
  pause
  exit /b 1
)

echo Opening frontend in browser...
start "" "%FRONTEND_URL%"

echo Starting Cloudflare Quick Tunnel in a separate window...
call :StartCloudflareTunnel

echo Startup complete.
exit /b 0

:project_error
echo Required project files/folders not found in current folder.
pause
exit /b 1

:WaitForBackendHealth
set /a BACKEND_HEALTH_ATTEMPTS=0
:wait_backend_health
set /a BACKEND_HEALTH_ATTEMPTS+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %BACKEND_HEALTH_ATTEMPTS% GEQ 40 (
  echo [ERROR] Backend healthcheck werd niet op tijd groen.
  docker compose logs backend --tail 80
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
  docker compose logs frontend --tail 80
  pause
  exit /b 1
)
timeout /t 2 >nul
goto wait_frontend_ready

:EnsureDockerRunning
echo Checking if Docker engine is running...
docker info >nul 2>&1
if %errorlevel% equ 0 exit /b 0
echo Docker engine not running.
echo Attempting to start Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker engine...
:waitdocker
timeout /t 5 >nul
docker info >nul 2>&1
if %errorlevel% neq 0 goto waitdocker
exit /b 0

:CleanupLegacyRezzervStacks
set "LEGACY_FOUND="
for %%N in (rezzerv-dev-frontend-1 rezzerv-dev-backend-1 rezzerv-dev-db-1) do (
  docker ps -a --format "{{.Names}}" | findstr /I /X "%%N" >nul
  if !errorlevel! equ 0 (
    set "LEGACY_FOUND=1"
    echo     Removing explicitly known legacy container %%N ...
    docker stop %%N >nul 2>&1
    docker rm %%N >nul 2>&1
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
    docker rm !CONTAINER_NAME! >nul 2>&1
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
  "$isWslRelayName = $name -match '(?i)^wslrelay\.exe$';" ^
  "$isWslRelayCmd = $cmd.ToLowerInvariant() -match '--vm-id|wslrelay';" ^
  "$isWslRuntime = $isWslRelayName -or $isWslRelayCmd;" ^
  "$isRezzerv = $sig -match 'rezzerv';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\.exe$|(?i)^powershell\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|vite');" ^
  "if ($isDocker) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isWslRuntime) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded WSL/runtime process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="12" echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  if not "%errorlevel%"=="12" echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
  pause
  exit /b 1
)
exit /b 0

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
