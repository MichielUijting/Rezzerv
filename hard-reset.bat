@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"
set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"

echo ========================================
echo       Rezzerv Hard Reset Routine
echo ========================================
echo LET OP: deze routine verwijdert bewust de databasevolume.
echo Gebruik start.bat voor een normale persistente start.

call :EnsureDockerRunning || exit /b 1

echo [1/6] Stopping containers and removing volumes...
docker compose down --volumes --remove-orphans
if %errorlevel% neq 0 echo [WARN] docker compose down gaf een foutcode. Doorgaan met schone rebuild.

echo [1b/6] Removing legacy parallel Rezzerv stacks if present...
call :CleanupLegacyRezzervStacks || exit /b 1

echo [2/6] Checking frontend ports for leftover listeners...
call :CleanupPortIfRezzerv %STALE_FRONTEND_PORT% || exit /b 1
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1
call :TryStopOldRezzervOnPort %STALE_FRONTEND_PORT% %REZZERV_VERSION% || exit /b 1

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

:CleanupLegacyRezzervStacks
set "LEGACY_FOUND="
for /f "usebackq delims=" %%C in (`docker ps -aq --filter "name=^rezzerv-dev-"`) do (
  set "LEGACY_FOUND=1"
  echo     Removing legacy container %%C from compose project rezzerv-dev...
  docker stop %%C >nul 2>&1
  docker rm %%C >nul 2>&1
)
for /f "usebackq delims=" %%C in (`docker ps -aq --filter "name=^rezzerv_dev-"`) do (
  set "LEGACY_FOUND=1"
  echo     Removing legacy container %%C from compose project rezzerv_dev...
  docker stop %%C >nul 2>&1
  docker rm %%C >nul 2>&1
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

:TryStopOldRezzervOnPort
set "TARGET_PORT=%~1"
set "TARGET_VERSION=%~2"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%TARGET_PORT%;" ^
  "$targetVersion='%TARGET_VERSION%';" ^
  "function GetVersion([string]$base) { try { $v = Invoke-RestMethod -Uri ($base + '/version.json') -TimeoutSec 3; if ($v.version) { return [string]$v.version } } catch {}; try { $resp = Invoke-WebRequest -Uri ($base + '/') -UseBasicParsing -TimeoutSec 3; $content=[string]$resp.Content; $m=[regex]::Match($content,'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)'); if ($m.Success) { return $m.Groups[1].Value } } catch {}; return '' }" ^
  "$base='http://localhost:' + $port;" ^
  "$servedVersion = GetVersion $base;" ^
  "if (-not $servedVersion) { exit 0 }" ^
  "if ($servedVersion -eq $targetVersion) { exit 0 }" ^
  "Write-Host ('[WARN] Port ' + $port + ' serves old Rezzerv version ' + $servedVersion + ' while target is ' + $targetVersion + '. Attempting targeted cleanup...');" ^
  "$listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue; foreach ($listener in $listeners) { $owningPid = $listener.OwningProcess; $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue; if (-not $proc) { continue }; $name=[string]$proc.Name; $cmd=[string]$proc.CommandLine; $sig=($name + ' ' + $cmd).ToLowerInvariant(); $isDocker=$name -match '(?i)^(docker|docker desktop|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$' -or $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby'; $isWsl=$name -match '(?i)^wslrelay\.exe$' -or $cmd.ToLowerInvariant() -match '--vm-id|wslrelay'; if ($isDocker -or $isWsl) { continue }; if ($sig -match 'rezzerv|vite|node|npm') { Stop-Process -Id $owningPid -Force -ErrorAction SilentlyContinue } }" ^
  "Start-Sleep -Seconds 1; $remaining = GetVersion $base; if ($remaining -and $remaining -ne $targetVersion) { exit 24 } else { exit 0 }"
if %errorlevel% neq 0 exit /b 1
exit /b 0
