@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"
set "BACKEND_HEALTH_URL=http://localhost:8001/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

echo ========================================
echo        Rezzerv Startup Routine
echo Version: %REZZERV_VERSION%
echo ========================================
echo Modus: persistente normale start ^(databasevolume blijft behouden^)
echo Gebruik hard-reset.bat alleen voor een expliciete schone reset.

REM --- Build from local TEMP copy to avoid OneDrive placeholder/lock issues ---
set "BUILD_DIR=%TEMP%\rezzerv_build"
if exist "%BUILD_DIR%" (
  rmdir /s /q "%BUILD_DIR%" >nul 2>&1
)
mkdir "%BUILD_DIR%" >nul 2>&1

echo Kopieren naar lokale buildmap: %BUILD_DIR%
robocopy "%cd%" "%BUILD_DIR%" /MIR /XD ".git" /XF "*.zip" /NFL /NDL /NJH /NJS /R:1 /W:1 >nul
if %errorlevel% GEQ 8 (
  echo [ERROR] Kopieren naar buildmap mislukt.
  pause
  exit /b 1
)

pushd "%BUILD_DIR%"

echo Checking project structure...
if not exist "docker-compose.yml" (
  echo docker-compose.yml not found in current folder.
  pause
  exit /b 1
)
if not exist "backend" (
  echo backend folder not found in current folder.
  pause
  exit /b 1
)
if not exist "frontend" (
  echo frontend folder not found in current folder.
  pause
  exit /b 1
)

echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" (
      del /f /q "%%F" >nul 2>&1
    )
  )
)

echo Checking Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker is not installed. Please install Docker Desktop.
  pause
  exit /b 1
)

echo Checking if Docker engine is running...
docker info >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker engine not running.
  echo Attempting to start Docker Desktop...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  echo Waiting for Docker engine...
  :waitdocker
  timeout /t 5 >nul
  docker info >nul 2>&1
  if %errorlevel% neq 0 goto waitdocker
)

echo Validating docker-compose.yml...
docker compose config >nul 2>&1
if %errorlevel% neq 0 (
  echo docker-compose.yml is invalid. See errors above.
  docker compose config
  pause
  exit /b 1
)

echo Sanitizing previous Rezzerv runtime...
echo [1/6] Stopping existing compose stack and removing orphans...
docker compose down --remove-orphans >nul 2>&1

echo [2/6] Releasing stale frontend ports if needed...
call :KillPortIfListening %STALE_FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1
call :KillPortIfListening %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

echo [3/6] Building updated images...
docker compose build --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build failed.
  pause
  exit /b 1
)

echo [4/6] Starting containers without deleting data volume...
docker compose up -d --remove-orphans
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  pause
  exit /b 1
)

echo [5/6] Waiting for backend health...
where curl >nul 2>&1
if %errorlevel%==0 (
  :waithealth_curl
  timeout /t 3 >nul
  curl -s %BACKEND_HEALTH_URL% | find "ok" >nul
  if %errorlevel% neq 0 goto waithealth_curl
) else (
  :waithealth_ps
  timeout /t 3 >nul
  powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.status -ne 'ok') { exit 1 } } catch { exit 1 }" >nul 2>&1
  if %errorlevel% neq 0 goto waithealth_ps
)

echo [6/6] Verifying active frontend ports...
call :VerifyFrontendPorts
if %errorlevel% neq 0 (
  echo [ERROR] Frontend port verification failed.
  pause
  exit /b 1
)

echo Opening application...
start %FRONTEND_URL%

echo Startup complete.
pause
exit /b 0

:KillPortIfListening
set "TARGET_PORT=%~1"
set "FOUND_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
  set "FOUND_PID=%%P"
  goto :kill_found
)
goto :kill_done

:kill_found
echo     Port %TARGET_PORT% was still in use by PID !FOUND_PID! - stopping process...
taskkill /PID !FOUND_PID! /T /F >nul 2>&1
if !errorlevel! neq 0 (
  echo [ERROR] Could not stop process on port %TARGET_PORT%.
  exit /b 1
)
timeout /t 1 >nul
:kill_done
exit /b 0

:VerifyFrontendPorts
powershell -NoProfile -Command "$primary = Test-NetConnection -ComputerName localhost -Port %FRONTEND_PORT% -WarningAction SilentlyContinue; if (-not $primary.TcpTestSucceeded) { exit 1 }"
if %errorlevel% neq 0 (
  echo [ERROR] Expected frontend port %FRONTEND_PORT% is not reachable.
  exit /b 1
)
powershell -NoProfile -Command "$stale = Test-NetConnection -ComputerName localhost -Port %STALE_FRONTEND_PORT% -WarningAction SilentlyContinue; if ($stale.TcpTestSucceeded) { exit 1 }"
if %errorlevel% neq 0 (
  echo [ERROR] Old frontend port %STALE_FRONTEND_PORT% is still reachable after startup.
  exit /b 1
)
echo     Active frontend verified on port %FRONTEND_PORT%. No stale frontend on port %STALE_FRONTEND_PORT%.
exit /b 0
