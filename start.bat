@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"
set "BACKEND_HEALTH_URL=http://localhost:8001/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

echo ========================================
echo        Rezzerv Startup Routine
echo Version: %REZZERV_VERSION%
echo ========================================
echo Modus: persistente normale start ^(databasevolume blijft behouden^)
echo Gebruik hard-reset.bat alleen voor een expliciete schone reset.

REM --- Build from local TEMP copy to avoid OneDrive placeholder/lock issues ---
set "BUILD_DIR=%TEMP%\rezzerv_build"
if exist "%BUILD_DIR%" (
  rmdir /s /q "%BUILD_DIR%" >nul 2>&1
)
mkdir "%BUILD_DIR%" >nul 2>&1

echo Kopieren naar lokale buildmap: %BUILD_DIR%
robocopy "%cd%" "%BUILD_DIR%" /MIR /XD ".git" /XF "*.zip" /NFL /NDL /NJH /NJS /R:1 /W:1 >nul
if %errorlevel% GEQ 8 (
  echo [ERROR] Kopieren naar buildmap mislukt.
  pause
  exit /b 1
)

pushd "%BUILD_DIR%"

echo Checking project structure...
if not exist "docker-compose.yml" (
  echo docker-compose.yml not found in current folder.
  pause
  exit /b 1
)
if not exist "backend" (
  echo backend folder not found in current folder.
  pause
  exit /b 1
)
if not exist "frontend" (
  echo frontend folder not found in current folder.
  pause
  exit /b 1
)

echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" (
      del /f /q "%%F" >nul 2>&1
    )
  )
)

echo Checking Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker is not installed. Please install Docker Desktop.
  pause
  exit /b 1
)

call :EnsureDockerRunning
if %errorlevel% neq 0 exit /b 1

echo Validating docker-compose.yml...
docker compose config >nul 2>&1
if %errorlevel% neq 0 (
  echo docker-compose.yml is invalid. See errors above.
  docker compose config
  pause
  exit /b 1
)

echo Sanitizing previous Rezzerv runtime...
echo [1/7] Stopping existing compose stack and removing orphans...
docker compose down --remove-orphans >nul 2>&1

echo [2/7] Checking frontend ports for leftover listeners...
call :CleanupPortIfRezzerv %STALE_FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1
call :CleanupPortIfRezzerv %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

echo [3/7] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning
if %errorlevel% neq 0 exit /b 1

echo [4/7] Building updated images...
docker compose build --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build failed.
  pause
  exit /b 1
)

echo [5/7] Starting containers without deleting data volume...
docker compose up -d --remove-orphans
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  pause
  exit /b 1
)

echo [6/7] Waiting for backend health...
where curl >nul 2>&1
if %errorlevel%==0 (
  :waithealth_curl
  timeout /t 3 >nul
  curl -s %BACKEND_HEALTH_URL% | find "ok" >nul
  if %errorlevel% neq 0 goto waithealth_curl
) else (
  :waithealth_ps
  timeout /t 3 >nul
  powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.status -ne 'ok') { exit 1 } } catch { exit 1 }" >nul 2>&1
  if %errorlevel% neq 0 goto waithealth_ps
)

echo [7/7] Verifying active frontend ports...
call :VerifyFrontendPorts
if %errorlevel% neq 0 (
  echo [ERROR] Frontend port verification failed.
  pause
  exit /b 1
)

echo Opening application...
start %FRONTEND_URL%

echo Startup complete.
pause
exit /b 0

:EnsureDockerRunning
echo Checking if Docker engine is running...
docker info >nul 2>&1
if %errorlevel% equ 0 exit /b 0
echo Docker engine not running.
echo Attempting to start Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo Waiting for Docker engine...
:waitdocker
timeout /t 5 >nul
docker info >nul 2>&1
if %errorlevel% neq 0 goto waitdocker
exit /b 0

:CleanupPortIfRezzerv
set "TARGET_PORT=%~1"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%TARGET_PORT%;" ^
  "$listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if (-not $listener) { Write-Host ('    Port ' + $port + ' is free.'); exit 0 }" ^
  "$owningPid = $listener.OwningProcess;" ^
  "$proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue;" ^
  "$name = if ($proc) { $proc.Name } else { '' };" ^
  "$cmd = if ($proc) { [string]$proc.CommandLine } else { '' };" ^
  "$sig = ($name + ' ' + $cmd).ToLowerInvariant();" ^
  "$isDockerName = $name -match '(?i)^(docker|docker desktop|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$';" ^
  "$isDockerCmd = $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby';" ^
  "$isDocker = $isDockerName -or $isDockerCmd;" ^
  "$isWslRelayName = $name -match '(?i)^wslrelay\.exe$';" ^
  "$isWslRelayCmd = $cmd.ToLowerInvariant() -match '--vm-id|wslrelay';" ^
  "$isWslRuntime = $isWslRelayName -or $isWslRelayCmd;" ^
  "$isRezzerv = $sig -match 'rezzerv|rezzerv_build';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\\.exe$|(?i)^powershell\\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|rezzerv_build|vite');" ^
  "if ($isDocker) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isWslRuntime) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded WSL/runtime process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
set "PS_EXIT=%errorlevel%"
if "%PS_EXIT%"=="0" exit /b 0
if "%PS_EXIT%"=="11" (
  echo [ERROR] Veilige cleanup gestopt: uitgesloten proces gebruikt poort %TARGET_PORT%.
  pause
  exit /b 1
)
if "%PS_EXIT%"=="12" (
  echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  pause
  exit /b 1
)
echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
pause
exit /b 1

:VerifyFrontendPorts
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$currentVersion='%REZZERV_VERSION%';" ^
  "$primaryUrl='http://localhost:%FRONTEND_PORT%/';" ^
  "$staleUrl='http://localhost:%STALE_FRONTEND_PORT%/';" ^
  "try { $primary = Invoke-WebRequest -Uri $primaryUrl -UseBasicParsing -TimeoutSec 4 } catch { exit 21 }" ^
  "$primaryContent = [string]$primary.Content;" ^
  "$primaryVersion = [regex]::Match($primaryContent, 'Rezzerv v([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value;" ^
  "if (-not $primaryVersion) { $primaryVersion = [regex]::Match($primaryContent, 'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value }" ^
  "if (-not $primaryVersion) { exit 22 }" ^
  "if ($primaryVersion -ne $currentVersion) { Write-Host ('[ERROR] Active frontend on port %FRONTEND_PORT% serves version ' + $primaryVersion + ' instead of ' + $currentVersion + '.'); exit 23 }" ^
  "$staleResponse = $null;" ^
  "try { $staleResponse = Invoke-WebRequest -Uri $staleUrl -UseBasicParsing -TimeoutSec 3 } catch { exit 0 }" ^
  "$staleContent = [string]$staleResponse.Content;" ^
  "$staleVersion = [regex]::Match($staleContent, 'Rezzerv v([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value;" ^
  "if (-not $staleVersion) { $staleVersion = [regex]::Match($staleContent, 'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value }" ^
  "if (-not $staleVersion) { Write-Host ('[INFO] Port %STALE_FRONTEND_PORT% is reachable but does not appear to serve a Rezzerv frontend. Action: ignore'); exit 0 }" ^
  "Write-Host ('[WARN] Port %STALE_FRONTEND_PORT% serves stale Rezzerv frontend version ' + $staleVersion + '. Attempting targeted cleanup...');" ^
  "$candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $n = ($_.Name | Out-String).Trim().ToLowerInvariant(); $cl = ([string]$_.CommandLine).ToLowerInvariant(); (($n -match 'node|npm|vite|powershell|pwsh') -and ($cl -match '5173|rezzerv|vite')) -or ($cl -match 'localhost:5173') };" ^
  "$stopped = $false; foreach ($p in $candidates) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Host ('[INFO] Stopped stale frontend candidate PID ' + $p.ProcessId + ' (' + $p.Name + ').'); $stopped = $true } catch {} }" ^
  "Start-Sleep -Seconds 2;" ^
  "try { $recheck = Invoke-WebRequest -Uri $staleUrl -UseBasicParsing -TimeoutSec 3; $recheckContent = [string]$recheck.Content; $recheckVersion = [regex]::Match($recheckContent, 'Rezzerv v([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value; if (-not $recheckVersion) { $recheckVersion = [regex]::Match($recheckContent, 'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)').Groups[1].Value }; if ($recheckVersion) { Write-Host ('[ERROR] Old Rezzerv frontend on port %STALE_FRONTEND_PORT% is still active after cleanup. Version: ' + $recheckVersion); exit 24 } else { Write-Host ('[INFO] Port %STALE_FRONTEND_PORT% remains reachable but no longer serves a Rezzerv frontend. Action: ignore'); exit 0 } } catch { if ($stopped) { Write-Host ('[INFO] Stale frontend on port %STALE_FRONTEND_PORT% is no longer reachable after cleanup.'); } exit 0 }"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="21" echo [ERROR] Expected frontend port %FRONTEND_PORT% is not reachable.
  if "%errorlevel%"=="22" echo [ERROR] Active frontend on port %FRONTEND_PORT% does not expose a detectable Rezzerv version.
  if "%errorlevel%"=="23" rem message already printed by PowerShell
  if "%errorlevel%"=="24" rem message already printed by PowerShell
  exit /b 1
)
echo     Active frontend verified on port %FRONTEND_PORT%. No stale Rezzerv frontend remains on port %STALE_FRONTEND_PORT%.
exit /b 0
