@echo off
setlocal
set "SCRIPT=%~dp0po-test-pr251-v011296.ps1"
if not exist "%SCRIPT%" (
  echo LAUNCHER_ERROR: PowerShell-runner niet gevonden naast deze starter:
  echo "%SCRIPT%"
  echo.
  pause
  exit /b 2
)
if /I "%~1"=="-SelfTest" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -SelfTest
  exit /b %ERRORLEVEL%
)
if /I "%~1"=="-HoldProbe" (
  %ComSpec% /d /k "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%"" -SelfTest & echo PO_TEST_LAUNCHER_HOLD_PATH_GREEN & exit"
  exit /b %ERRORLEVEL%
)
echo Rezzerv PO-test PR #251 wordt gestart.
echo Dit venster blijft na afloop of bij een fout open.
echo.
%ComSpec% /d /k "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""%SCRIPT%"""
exit /b %ERRORLEVEL%
