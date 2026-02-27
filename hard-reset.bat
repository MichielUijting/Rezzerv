@echo off
echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================

echo Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans

echo Removing old images (ignore errors)...
docker image rm rezzerv-frontend -f >nul 2>&1
docker image rm rezzerv-backend -f >nul 2>&1

echo Rebuilding without cache...
docker compose build --no-cache
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build --no-cache failed.
  exit /b 1
)

echo Starting containers (no rebuild; use freshly built images)...
docker compose up -d
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  exit /b 1
)

exit /b 0
