@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%po-test-pr252-v0112105.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Rezzerv PO-test v01.12.105 is GROEN.
) else (
  echo Rezzerv PO-test v01.12.105 eindigde met exitcode %RC%.
)
echo.
pause
exit /b %RC%
