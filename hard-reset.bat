@echo off
setlocal EnableExtensions EnableDelayedExpansion

if "%REZZERV_VERSION%"=="" (
  for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
)

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"

echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================
echo LET OP: deze routine verwijdert bewust de databasevolume.
echo Gebruik start.bat voor een normale persistente start.

echo [1/5] Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans
if %errorlevel% neq 0 (
  echo [WARN] docker compose down gaf een foutcode. Doorgaan met schone rebuild.
)

echo [2/5] Releasing stale frontend ports if needed...
call :KillPortIfListening %STALE_FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1
call :KillPortIfListening %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

echo [3/5] Rebuilding images without cache...
echo Dit kan enkele minuten duren. Docker build-output volgt hieronder.
docker compose build --no-cache --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build --no-cache failed.
  exit /b 1
)

echo [4/5] Starting containers...
docker compose up -d --remove-orphans
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  exit /b 1
)

echo [5/5] Hard reset completed successfully.
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
