@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-InHuis-Standalone.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo BUILD MISLUKT. Bekijk releaseuild.log.
if "%RESULT%"=="0" echo Build afgerond. Bekijk de release-map.
pause
exit /b %RESULT%
