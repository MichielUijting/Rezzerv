@echo off
setlocal EnableExtensions
set "FRONTEND_URL=%~1"
if "%FRONTEND_URL%"=="" set "FRONTEND_URL=http://localhost:5174"
set "TUNNEL_LOG=%TEMP%\rezzerv_cloudflare_tunnel.log"

echo ========================================
echo     Rezzerv Cloudflare Quick Tunnel
echo ========================================
echo Frontend: %FRONTEND_URL%
echo.

del /f /q "%TUNNEL_LOG%" >nul 2>&1
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] cloudflared is not installed or not on PATH.
  echo Install it first, then rerun this script.
  pause
  exit /b 1
)

echo A new HTTPS tunnel URL will appear below.
echo Keep this window open while testing Rezzerv on Android.
echo.
powershell -NoLogo -NoExit -ExecutionPolicy Bypass -Command "$url='%FRONTEND_URL%'; $log='%TUNNEL_LOG%'; Write-Host ('Starting Cloudflare Quick Tunnel for ' + $url) -ForegroundColor Cyan; Write-Host 'Copy the https://...trycloudflare.com URL below to your Android phone.' -ForegroundColor Yellow; & cloudflared tunnel --url $url 2>&1 | Tee-Object -FilePath $log"

