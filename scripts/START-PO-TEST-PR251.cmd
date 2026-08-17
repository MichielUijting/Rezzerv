@echo off
setlocal
set "SCRIPT=%~dp0po-test-pr251-v011296.ps1"
if not exist "%SCRIPT%" (
  echo LAUNCHER_ERROR: PowerShell-runner niet gevonden naast deze starter:
  echo "%SCRIPT%"
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "EXITCODE=%ERRORLEVEL%"
if /I "%~1"=="-SelfTest" exit /b %EXITCODE%
echo.
echo De PO-test is afgerond. Controleer hierboven TESTRESULTAAT en Cleanup afgerond.
pause
exit /b %EXITCODE%
