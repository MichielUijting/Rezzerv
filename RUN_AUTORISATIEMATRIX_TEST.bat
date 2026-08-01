@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo Rezzerv autorisatiematrix acceptatietest v1.1
echo ============================================================
echo.

docker compose ps backend >nul 2>&1
if errorlevel 1 (
  echo FOUT: Docker Compose of de backendcontainer is niet beschikbaar.
  echo Start Rezzerv eerst met: docker compose up -d
  echo.
  pause
  exit /b 1
)

docker compose exec -T backend python -m app.testing.authorization_matrix_acceptance
set TEST_EXIT=%ERRORLEVEL%

echo.
if "%TEST_EXIT%"=="0" (
  echo RESULTAAT: GO - de runtime komt overeen met autorisatiematrix v1.1.
) else (
  echo RESULTAAT: NO-GO - er zijn afwijkingen gevonden.
)
echo.
pause
exit /b %TEST_EXIT%
