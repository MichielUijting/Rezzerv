@echo off
echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================

echo Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans

echo Removing old images (ignore errors)...
echo - Removing image: rezzerv-frontend (can take a moment)...
docker image rm rezzerv-frontend -f >nul 2>&1
echo   done.
echo - Removing image: rezzerv-backend (can take a moment)...
docker image rm rezzerv-backend -f >nul 2>&1
echo   done.

echo Rebuilding without cache... (this can take several minutes and will show build output)
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
