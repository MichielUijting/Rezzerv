@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"
set "FRONTEND_PORT=5174"

echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================
echo LET OP: deze routine verwijdert bewust de databasevolume.
echo Gebruik start.bat voor een normale persistente start.

if exist "validate-version-sync.bat" (
  call validate-version-sync.bat
  if %errorlevel% neq 0 (
    echo [ERROR] Versiesync-check gefaald. Hard reset wordt afgebroken.
    pause
    exit /b 1
  )
) else (
  echo [WARN] validate-version-sync.bat niet gevonden. Doorgaan zonder versiesync-check.
)

call :EnsureDockerRunning || exit /b 1

echo [1/6] Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans
if %errorlevel% neq 0 echo [WARN] docker compose down gaf een foutcode. Doorgaan met schone rebuild.

echo [1b/6] Removing legacy parallel Rezzerv stacks if present...
call :CleanupLegacyRezzervStacks || exit /b 1

echo [2/6] Checking active frontend port for leftover listeners...
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1

echo [3/6] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning || exit /b 1

echo [4/6] Rebuilding images without cache...
echo Dit kan enkele minuten duren. Docker build-output volgt hieronder.
docker compose build --no-cache --pull
if %errorlevel% neq 0 (
  echo [ERROR] docker compose build --no-cache failed.
  exit /b 1
)

echo [5/6] Starting containers...
docker compose up -d --remove-orphans --force-recreate
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

:CleanupLegacyRezzervStacks
set "LEGACY_FOUND="
for %%N in (rezzerv-dev-frontend-1 rezzerv-dev-backend-1 rezzerv-dev-db-1) do (
  docker ps -a --format "{{.Names}}" | findstr /I /X "%%N" >nul
  if !errorlevel! equ 0 (
    set "LEGACY_FOUND=1"
    echo     Removing explicitly known legacy container %%N ...
    docker stop %%N >nul 2>&1
    docker rm %%N >nul 2>&1
  )
)
for /f "usebackq delims=" %%N in (`docker ps -a --format "{{.Names}}"`) do (
  set "CONTAINER_NAME=%%N"
  set "IS_LEGACY="
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv-dev-" set "IS_LEGACY=1"
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv_dev_" set "IS_LEGACY=1"
  if /I not "!CONTAINER_NAME:~0,14!"=="rezzerv_build-" if defined IS_LEGACY (
    set "LEGACY_FOUND=1"
    echo     Removing legacy container !CONTAINER_NAME! ...
    docker stop !CONTAINER_NAME! >nul 2>&1
    docker rm !CONTAINER_NAME! >nul 2>&1
  )
)
if not defined LEGACY_FOUND echo     No legacy parallel Rezzerv stack detected.
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
  "$isRezzerv = $sig -match 'rezzerv';" ^
  "$isNodeLike = $sig -match 'node|npm|vite';" ^
  "$isPowerShellRezzerv = ($name -match '(?i)^pwsh\.exe$|(?i)^powershell\.exe$') -and ($cmd.ToLowerInvariant() -match 'rezzerv|vite');" ^
  "if ($isDocker) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isWslRuntime) { Write-Host ('[INFO] Port ' + $port + ' is occupied by excluded WSL/runtime process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd + '. Action: ignore'); exit 0 }" ^
  "if ($isRezzerv -or $isNodeLike -or $isPowerShellRezzerv) { Write-Host ('    Port ' + $port + ' is occupied by leftover Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') - stopping process...'); Stop-Process -Id $owningPid -Force -ErrorAction Stop; Start-Sleep -Seconds 1; exit 0 }" ^
  "Write-Host ('[ERROR] Port ' + $port + ' is occupied by unknown process PID ' + $owningPid + ' (' + $name + '). Command: ' + $cmd); exit 12"
if %errorlevel% neq 0 exit /b 1
exit /b 0
