@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo Rezzerv autorisatiematrix acceptatietest v1.1
echo ============================================================
echo.

echo Stap 1 van 3: actuele backend-image bouwen...
docker compose build backend
if errorlevel 1 (
  echo.
  echo FOUT: de backend-image kon niet worden gebouwd.
  echo Controleer of Docker Desktop actief is.
  echo.
  pause
  exit /b 1
)

echo.
echo Stap 2 van 3: backendcontainer vernieuwen...
docker compose up -d --force-recreate backend
if errorlevel 1 (
  echo.
  echo FOUT: de backendcontainer kon niet worden vernieuwd.
  echo.
  pause
  exit /b 1
)

echo.
echo Stap 3 van 3: autorisatiematrix controleren...
docker compose exec -T backend python -m app.testing.authorization_matrix_acceptance
set TEST_EXIT=%ERRORLEVEL%

echo.
if "%TEST_EXIT%"=="0" (
  echo RESULTAAT: GO - de runtime komt overeen met autorisatiematrix v1.1.
) else (
  echo RESULTAAT: NO-GO - de test is mislukt of er zijn afwijkingen gevonden.
)
echo.
pause
exit /b %TEST_EXIT%
