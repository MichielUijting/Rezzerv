@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
echo ========================================
echo   Rezzerv lokale backend-check
echo ========================================
python start_local_backend.py --check-only
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [FOUT] De lokale backend-check is niet geslaagd.
  echo Sluit dit venster niet zonder screenshot als je deze melding aan het scrumteam doorgeeft.
) else (
  echo.
  echo [OK] De lokale backend-check is geslaagd.
)
pause
exit /b %RC%
