@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "REPO_DIR=%CD%"
set "COMPOSE_ENV="
set "FRONTEND_PORT=5174"
set "BACKEND_PORT=8011"
set "BACKEND_HEALTH_URL=http://localhost:%BACKEND_PORT%/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
set "DOCKER_DESKTOP_EXE=C:\Program Files\Docker\Docker\Docker Desktop.exe"
set "REZZERV_VERSION="

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"
set "REZZERV_VERSION=%REZZERV_VERSION%"

echo ========================================
echo        Rezzerv Startup Routine
echo Projectmap: %CD%
echo Version: %REZZERV_VERSION%
echo ========================================
echo Modus: stabiele Docker-opstart ^(zonder git-sync^)
echo.

call :ResolveProjectRoot || exit /b 1
set "REPO_DIR=%CD%"

if exist ".env" set "COMPOSE_ENV=--env-file .env"

echo.
echo === DEBUG INFO ===
echo Huidige directory:
cd
echo.
echo Bestanden:
dir /b
echo ==================
echo.

call :ValidateProjectStructure || exit /b 1
call :EnsureDockerRunning || exit /b 1
call :SanitizeRepoRuntimeArtifacts || exit /b 1
call :ValidateCompose || exit /b 1
call :CleanupLegacyRezzervStacks || exit /b 1
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1
call :CleanupPortIfRezzerv %BACKEND_PORT% || exit /b 1

echo [1/6] Stopping existing compose stack and removing orphans...
docker compose %COMPOSE_ENV% down --remove-orphans >nul 2>&1
docker compose %COMPOSE_ENV% rm -f -s -v >nul 2>&1

echo [2/6] Building images from projectmap...
docker compose %COMPOSE_ENV% build --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build failed.
  pause
  exit /b 1
)

echo [3/6] Starting stack from projectmap...
docker compose %COMPOSE_ENV% up -d --build --force-recreate
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  docker compose %COMPOSE_ENV% ps -a
  docker compose %COMPOSE_ENV% logs --tail 120
  pause
  exit /b 1
)

echo [4/6] Forcing frontend container onto the latest image...
docker compose %COMPOSE_ENV% up -d --force-recreate frontend
if %errorlevel% neq 0 (
  echo [ERROR] frontend force-recreate failed.
  docker compose %COMPOSE_ENV% ps -a
  docker compose %COMPOSE_ENV% logs frontend --tail 120
  pause
  exit /b 1
)

echo [5/6] Waiting for backend and frontend...
call :WaitForBackendHealth || exit /b 1
call :VerifyRuntimeDatabase || exit /b 1
call :WaitForFrontend %FRONTEND_URL% || exit /b 1
call :VerifyFrontendVersion || exit /b 1

echo [6/6] Opening frontend in browser...
start "" "%FRONTEND_URL%"

echo Startup complete.
exit /b 0

:ResolveProjectRoot
if exist "docker-compose.yml" exit /b 0
for /d %%d in (*) do (
  if exist "%%d\docker-compose.yml" (
    echo [INFO] Projectroot gevonden in submap %%d
    cd /d "%%d"
    exit /b 0
  )
)
echo [ERROR] Geen geldige projectroot gevonden.
echo Verwacht: docker-compose.yml in de huidige map of in exact één directe submap.
pause
exit /b 1

:ValidateProjectStructure
echo Valideren van projectstructuur...
if not exist "docker-compose.yml" goto :project_error
if not exist "backend" goto :project_error
if not exist "frontend" goto :project_error
if not exist "backend\data" mkdir "backend\data" >nul 2>&1
if not exist "backend\data" (
  echo [ERROR] backend\data ontbreekt en kon niet worden aangemaakt.
  pause
  exit /b 1
)
if exist "rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: rezzerv.db
  pause
  exit /b 1
)
if exist "backend\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: backend\rezzerv.db
  pause
  exit /b 1
)
if exist "validate-version-sync.bat" (
  call validate-version-sync.bat
  if %errorlevel% neq 0 (
    echo [ERROR] Versiesync-check gefaald. Start wordt afgebroken.
    pause
    exit /b 1
  )
)
exit /b 0

:ValidateCompose
echo Validating docker-compose.yml...
docker compose %COMPOSE_ENV% config >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] docker-compose.yml is invalid.
  docker compose %COMPOSE_ENV% config
  pause
  exit /b 1
)
findstr /I /C:"./backend/data:/app/data" "docker-compose.yml" >nul
if errorlevel 1 (
  echo [ERROR] docker-compose.yml mount niet conform runtime-regel.
  echo Verwacht: ./backend/data:/app/data
  pause
  exit /b 1
)
exit /b 0

:SanitizeRepoRuntimeArtifacts
echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" del /f /q "%%F" >nul 2>&1
  )
)
if exist "%cd%\frontend\dist" rmdir /s /q "%cd%\frontend\dist"
if exist "%cd%\frontend\node_modules\.vite" rmdir /s /q "%cd%\frontend\node_modules\.vite"
if exist "%cd%\frontend\.vite" rmdir /s /q "%cd%\frontend\.vite"
for /r "%cd%" %%f in (*.pyc) do del /q "%%f" 2>nul
for /d /r "%cd%" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul
exit /b 0

:EnsureDockerRunning
echo Checking Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Docker is not installed.
  pause
  exit /b 1
)
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
echo Opruimen van legacy Docker runtimes...
set "LEGACY_FOUND="
for /f "usebackq delims=" %%N in (`docker ps -a --format "{{.Names}}"`) do (
  set "CONTAINER_NAME=%%N"
  set "IS_LEGACY="
  if /I "!CONTAINER_NAME:~0,14!"=="rezzerv_build-" set "IS_LEGACY=1"
  if /I "!CONTAINER_NAME:~0,14!"=="rezzerv-build-" set "IS_LEGACY=1"
  if defined IS_LEGACY (
    set "LEGACY_FOUND=1"
    echo     Removing legacy container !CONTAINER_NAME! ...
    docker stop !CONTAINER_NAME! >nul 2>&1
    docker rm -f !CONTAINER_NAME! >nul 2>&1
  )
)
if not defined LEGACY_FOUND echo     No legacy rezzerv_build stack detected.
exit /b 0

:CleanupPortIfRezzerv
set "TARGET_PORT=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%TARGET_PORT%;" ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if (-not $listener) { Write-Host ('    Port ' + $port + ' is free.'); exit 0 }" ^
  "$owningPid = $listener.OwningProcess;" ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue;" ^
  "$name = if ($proc) { [string]$proc.Name } else { '' };" ^
  "$cmd = if ($proc) { [string]$proc.CommandLine } else { '' };" ^
  "$sig = ($name + ' ' + $cmd).ToLowerInvariant();" ^
  "$isDockerName = $name -match '(?i)^(docker|docker desktop|com\\.docker\\.backend|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$';" ^
  "$isDockerCmd = $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby';" ^
  "$isDocker = $isDockerName -or $isDockerCmd;" ^
  "$isWslRelayName = $name -match '(?i)^wslrelay\\.exe$';" ^
  "$isWslRelayCmd = $cmd.ToLowerInvariant() -match '--vm-id|wslrelay';" ^
  "$isWslRuntime = $isWslRelayName -or $isWslRelayCmd;" ^
  "$isRezzerv = $sig -match 'rezzerv';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\\.exe$|(?i)^powershell\\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|vite');" ^
  "if ($isDocker) { Write-Host ('[INFO] Port ' + $port + ' is occupied by Docker process PID ' + $owningPid + ' (' + $name + '). Action: allow cleanup to continue'); exit 0 }" ^
  "if ($isWslRuntime) { Write-Host ('[INFO] Port ' + $port + ' is occupied by WSL/runtime process PID ' + $owningPid + ' (' + $name + '). Action: allow cleanup to continue'); exit 0 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="12" echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  if not "%errorlevel%"=="12" echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
  pause
  exit /b 1
)
exit /b 0

:WaitForBackendHealth
set /a BACKEND_HEALTH_ATTEMPTS=0
:wait_backend_health
set /a BACKEND_HEALTH_ATTEMPTS+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.status -eq 'ok') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if %errorlevel% equ 0 exit /b 0
if %BACKEND_HEALTH_ATTEMPTS% GEQ 40 (
  echo [ERROR] Backend healthcheck werd niet op tijd groen.
  docker compose %COMPOSE_ENV% logs backend --tail 120
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
  docker compose %COMPOSE_ENV% logs frontend --tail 120
  pause
  exit /b 1
)
timeout /t 2 >nul
goto wait_frontend_ready

:VerifyFrontendVersion
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$expected='%REZZERV_VERSION%';" ^
  "$resp = Invoke-RestMethod -Uri '%FRONTEND_URL%/version.json' -TimeoutSec 3;" ^
  "$actual = [string]$resp.version;" ^
  "if ($actual -ne $expected) { Write-Host ('[ERROR] Frontend version mismatch. Expected ' + $expected + ' but got ' + $actual); exit 41 }" ^
  "Write-Host ('    Active frontend verified on port %FRONTEND_PORT% with version ' + $actual + '.'); exit 0"
if %errorlevel% neq 0 (
  echo [ERROR] Frontend version-validatie gefaald.
  pause
  exit /b 1
)
exit /b 0

:project_error
echo Required project files/folders not found in current folder.
pause
exit /b 1
