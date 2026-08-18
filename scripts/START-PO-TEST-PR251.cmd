@echo off
setlocal EnableExtensions
set "SCRIPT=%~dp0po-test-pr251-v011297.ps1"

if not exist "%SCRIPT%" (
  echo.
  echo PO-TEST ERROR: %SCRIPT% ontbreekt.
  echo Haal eerst de actuele PR #251 op in de lokale Rezzerv-repository.
  echo.
  pause
  exit /b 2
)

if /I "%~1"=="-SelfTest" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -SelfTest
  exit /b %ERRORLEVEL%
)

echo ============================================================
echo Rezzerv PO-test - Rezzerv-MVP-v01.12.97
echo PR #251 - Artikeldetail Voorraad
echo ============================================================
echo De test gebruikt een detached worktree en een kopie van rezzerv.db.
echo De live database wordt niet teruggeschreven.
echo Dit venster blijft na afloop open.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
echo PO-test gestopt of afgerond. Exitcode: %EXITCODE%
echo Controleer hierboven TESTRESULTAAT en Cleanup afgerond.
echo ============================================================
pause
exit /b %EXITCODE%
