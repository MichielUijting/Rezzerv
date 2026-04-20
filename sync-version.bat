@echo off
setlocal EnableExtensions EnableDelayedExpansion

if not "%1"=="" (
  echo %1 > VERSION.txt
)

set "VERSION="
for /f "usebackq delims=" %%v in ("VERSION.txt") do set "VERSION=%%v"

if "%VERSION%"=="" (
  echo [ERROR] VERSION.txt is leeg.
  exit /b 1
)

echo Syncing version: %VERSION%

echo {"version": "%VERSION%"} > version.json

echo {"version": "%VERSION%"} > frontend\version.json

echo {"version": "%VERSION%"} > frontend\public\version.json

REM Convert 01.13.00 -> 1.13.0
for /f "tokens=1-3 delims=." %%a in ("%VERSION%") do (
  set MAJOR=%%a
  set MINOR=%%b
  set PATCH=%%c
)

set MAJOR=%MAJOR:~1%
set PACKAGE_VERSION=%MAJOR%.%MINOR%.%PATCH%

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='frontend/package.json'; $json = Get-Content $p -Raw | ConvertFrom-Json; $json.version='%PACKAGE_VERSION%'; $json | ConvertTo-Json -Depth 10 | Set-Content $p"

echo [OK] Version gesynchroniseerd naar %VERSION% (%PACKAGE_VERSION%)
exit /b 0
