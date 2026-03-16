@echo off
setlocal EnableExtensions EnableDelayedExpansion

if "%REZZERV_VERSION%"=="" (
  for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
)

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"

echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================
echo LET OP: deze routine verwijdert bewust de databasevolume.
echo Gebruik start.bat voor een normale persistente start.

call :EnsureDockerRunning
if %errorlevel% neq 0 exit /b 1

echo [1/6] Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans
if %errorlevel% neq 0 (
  echo [WARN] docker compose down gaf een foutcode. Doorgaan met schone rebuild.
)

echo [2/6] Checking frontend ports for leftover listeners...
call :CleanupPortIfRezzerv %STALE_FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1
call :CleanupPortIfRezzerv %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

echo [3/6] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning
if %errorlevel% neq 0 exit /b 1

echo [4/6] Rebuilding images without cache...
echo Dit kan enkele minuten duren. Docker build-output volgt hieronder.
docker compose build --no-cache --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build --no-cache failed.
  exit /b 1
)

echo [5/6] Starting containers...
docker compose up -d --remove-orphans
if %errorlevel% neq 0 (
  echo [ERROR] docker compose up failed.
  exit /b 1
)

echo [6/6] Hard reset completed successfully.
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
  "$isRezzerv = $sig -match 'rezzerv|rezzerv_build';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\\.exe$|(?i)^powershell\\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|rezzerv_build|vite');" ^
  "if ($isDocker) { Write-Host ('[ERROR] Port ' + $port + ' is occupied by excluded process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 11 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
set "PS_EXIT=%errorlevel%"
if "%PS_EXIT%"=="0" exit /b 0
if "%PS_EXIT%"=="11" (
  echo [ERROR] Veilige cleanup gestopt: uitgesloten proces gebruikt poort %TARGET_PORT%.
  exit /b 1
)
if "%PS_EXIT%"=="12" (
  echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  exit /b 1
)
echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
exit /b 1
