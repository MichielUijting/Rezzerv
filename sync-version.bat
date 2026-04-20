@echo off
setlocal EnableExtensions EnableDelayedExpansion

if not "%~1"=="" (
  > VERSION.txt echo %~1
)

set "VERSION="
for /f "usebackq delims=" %%v in ("VERSION.txt") do set "VERSION=%%v"

if "%VERSION%"=="" (
  echo [ERROR] VERSION.txt is leeg.
  exit /b 1
)

for /f "usebackq delims=" %%s in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$version = Get-Content 'VERSION.txt' -Raw;" ^
  "$version = $version.Trim();" ^
  "$match = [regex]::Match($version, '(\d+)\.(\d+)\.(\d+)$');" ^
  "if (-not $match.Success) { throw 'Kon semver niet uit VERSION.txt halen.' }" ^
  "$major = [int]$match.Groups[1].Value;" ^
  "$minor = [int]$match.Groups[2].Value;" ^
  "$patch = [int]$match.Groups[3].Value;" ^
  "Write-Output ($major.ToString() + '.' + $minor.ToString() + '.' + $patch.ToString())"`) do set "PACKAGE_VERSION=%%s"

if "%PACKAGE_VERSION%"=="" (
  echo [ERROR] packageversie kon niet worden bepaald.
  exit /b 1
)

echo Syncing version: %VERSION%

> version.json echo {"version": "%VERSION%"}
> frontend\version.json echo {"version": "%VERSION%"}
> frontend\public\version.json echo {"version": "%VERSION%"}

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='frontend/package.json';" ^
  "$json = Get-Content $p -Raw | ConvertFrom-Json;" ^
  "$json.version='%PACKAGE_VERSION%';" ^
  "$json | ConvertTo-Json -Depth 20 | Set-Content $p"

if exist backend\VERSION.txt > backend\VERSION.txt echo %VERSION%

echo [OK] Version gesynchroniseerd naar %VERSION% (%PACKAGE_VERSION%)
exit /b 0
