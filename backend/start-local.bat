@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo ========================================
echo   Rezzerv lokale backend-start
echo ========================================
python start_local_backend.py --host 127.0.0.1 --port 8000
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [FOUT] De lokale backend is niet gestart.
  echo Maak een screenshot van deze melding voor het scrumteam.
  pause
)
exit /b %RC%
