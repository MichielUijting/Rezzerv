@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if not exist "VERSION.txt" (
  echo [ERROR] VERSION.txt ontbreekt.
  exit /b 1
)

set "CURRENT_VERSION="
set /p CURRENT_VERSION=<VERSION.txt
if not defined CURRENT_VERSION (
  echo [ERROR] VERSION.txt is leeg.
  exit /b 1
)

set "NEXT_VERSION="
for /f "usebackq delims=" %%n in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$v = (Get-Content 'VERSION.txt' -Raw).Trim();" ^
  "$m = [regex]::Match($v, '^(.*?)(\d+)\.(\d+)\.(\d+)$');" ^
  "if (-not $m.Success) { throw 'Ongeldig Rezzerv-versieformaat.' };" ^
  "$prefix = $m.Groups[1].Value;" ^
  "$major = [int]$m.Groups[2].Value;" ^
  "$minor = [int]$m.Groups[3].Value;" ^
  "$patch = [int]$m.Groups[4].Value + 1;" ^
  "Write-Output ($prefix + ('{0:D2}.{1:D2}.{2:D2}' -f $major, $minor, $patch))"`) do set "NEXT_VERSION=%%n"

if not defined NEXT_VERSION (
  echo [ERROR] Volgende versie kon niet worden bepaald.
  exit /b 2
)

call sync-version.bat "%NEXT_VERSION%"
if errorlevel 1 exit /b 3

call validate-version-sync.bat
if errorlevel 1 exit /b 4

echo [OK] Applicatieversie verhoogd: %CURRENT_VERSION% ^> %NEXT_VERSION%
exit /b 0
