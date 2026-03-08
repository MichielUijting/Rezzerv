@echo off
setlocal

if "%REZZERV_VERSION%"=="" (
  for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
)

echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================

echo [1/4] Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans
if %errorlevel% neq 0 (
  echo [WARN] docker compose down gaf een foutcode. Doorgaan met schone rebuild.
)

echo [2/4] Rebuilding images without cache...
echo Dit kan enkele minuten duren. Docker build-output volgt hieronder.
docker compose build --no-cache
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build --no-cache failed.
  exit /b 1
)

echo [3/4] Starting containers...
docker compose up -d
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  exit /b 1
)

echo [4/4] Hard reset completed successfully.
exit /b 0
