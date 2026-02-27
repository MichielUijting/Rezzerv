@echo off
echo ========================================
echo        Rezzerv Startup Routine
for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"
echo Version: %REZZERV_VERSION%
echo ========================================


REM --- Build from local TEMP copy to avoid OneDrive placeholder/lock issues ---
set "BUILD_DIR=%TEMP%\rezzerv_build"
if exist "%BUILD_DIR%" (
  rmdir /s /q "%BUILD_DIR%" >nul 2>&1
)
mkdir "%BUILD_DIR%" >nul 2>&1

echo Kopieren naar lokale buildmap: %BUILD_DIR%
REM /MIR: spiegel, /NFL /NDL: minder logging, /NJH /NJS: minder header, /R:1 /W:1: snel falen
robocopy "%cd%" "%BUILD_DIR%" /MIR /XD ".git" /XF "*.zip" /NFL /NDL /NJH /NJS /R:1 /W:1 >nul
if %errorlevel% GEQ 8 (
  echo [ERROR] Kopieren naar buildmap mislukt.
  popd
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

echo Cleaning accidental .dockerignore files (can break Docker builds)...
REM Keep intended dockerignore files in backend\ and frontend\
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

echo Performing HARD RESET (no-cache build + clean volumes/images)...
call hard-reset.bat
if %errorlevel% neq 0 (
  echo [ERROR] hard-reset failed.
  pause
  exit /b 1
)

echo Waiting for backend health...
where curl >nul 2>&1
if %errorlevel%==0 (
  :waithealth_curl
  timeout /t 3 >nul
  curl -s http://localhost:8000/api/health | find "ok" >nul
  if %errorlevel% neq 0 goto waithealth_curl
) else (
  :waithealth_ps
  timeout /t 3 >nul
  powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri http://localhost:8000/api/health -TimeoutSec 2; if ($r.status -ne 'ok') { exit 1 } } catch { exit 1 }" >nul 2>&1
  if %errorlevel% neq 0 goto waithealth_ps
)

echo Opening application...
start http://localhost:5173

echo Startup complete.
pause
