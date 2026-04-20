@echo off
setlocal EnableExtensions EnableDelayedExpansion

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

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='frontend/package.json'; $json = Get-Content $p -Raw | ConvertFrom-Json; $json.version='1.9.' + ($env:VERSION -split '\\.' | Select-Object -Last 1); $json | ConvertTo-Json -Depth 10 | Set-Content $p"

echo [OK] Version gesynchroniseerd.
exit /b 0
