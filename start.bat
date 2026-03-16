@echo off
setlocal EnableExtensions EnableDelayedExpansion

for /f "usebackq delims=" %%v in ("VERSION.txt") do set "REZZERV_VERSION=%%v"
if "%REZZERV_VERSION%"=="" set "REZZERV_VERSION=Rezzerv-unknown"

set "FRONTEND_PORT=5174"
set "STALE_FRONTEND_PORT=5173"
set "BACKEND_HEALTH_URL=http://localhost:8001/api/health"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
set "BUILD_DIR=%TEMP%\rezzerv_build"

 echo ========================================
 echo        Rezzerv Startup Routine
 echo Version: %REZZERV_VERSION%
 echo ========================================
 echo Modus: persistente normale start ^(databasevolume blijft behouden^)
 echo Gebruik hard-reset.bat alleen voor een expliciete schone reset.

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%" >nul 2>&1
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
if not exist "docker-compose.yml" goto :project_error
if not exist "backend" goto :project_error
if not exist "frontend" goto :project_error

echo Cleaning accidental .dockerignore files ^(can break Docker builds^)...
for /r %%F in (.dockerignore) do (
  if /I not "%%F"=="%cd%\frontend\.dockerignore" (
    if /I not "%%F"=="%cd%\backend\.dockerignore" del /f /q "%%F" >nul 2>&1
  )
)

echo Checking Docker installation...
docker --version >nul 2>&1
if %errorlevel% neq 0 (
  echo Docker is not installed. Please install Docker Desktop.
  pause
  exit /b 1
)

call :EnsureDockerRunning || exit /b 1

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

echo [1b/7] Removing legacy parallel Rezzerv stacks if present...
call :CleanupLegacyRezzervStacks || exit /b 1

echo [2/7] Checking frontend ports for leftover listeners...
call :CleanupPortIfRezzerv %STALE_FRONTEND_PORT% || exit /b 1
call :CleanupPortIfRezzerv %FRONTEND_PORT% || exit /b 1
call :TryStopOldRezzervOnPort %STALE_FRONTEND_PORT% %REZZERV_VERSION% || exit /b 1

echo [3/7] Re-checking Docker availability after cleanup...
call :EnsureDockerRunning || exit /b 1

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

:project_error
echo Required project files/folders not found in current folder.
pause
exit /b 1

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
for /f "usebackq delims=" %%N in (`docker ps -a --format "{{.Names}}"`) do (
  set "CONTAINER_NAME=%%N"
  set "IS_LEGACY="
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv-dev-" set "IS_LEGACY=1"
  if /I "!CONTAINER_NAME:~0,12!"=="rezzerv_dev-" set "IS_LEGACY=1"
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
if %errorlevel% neq 0 (
  if "%errorlevel%"=="12" echo [ERROR] Veilige cleanup gestopt: onbekend proces gebruikt poort %TARGET_PORT%.
  if not "%errorlevel%"=="12" echo [ERROR] Port cleanup failed unexpectedly for port %TARGET_PORT%.
  pause
  exit /b 1
)
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
  "if ($servedVersion -eq $targetVersion) { Write-Host ('[INFO] Port ' + $port + ' already serves current Rezzerv version ' + $servedVersion + '. Action: ignore'); exit 0 }" ^
  "Write-Host ('[WARN] Port ' + $port + ' serves old Rezzerv version ' + $servedVersion + ' while target is ' + $targetVersion + '. Attempting targeted cleanup...');" ^
  "$listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue; foreach ($listener in $listeners) { $owningPid = $listener.OwningProcess; $proc = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owningPid) -ErrorAction SilentlyContinue; if (-not $proc) { continue }; $name=[string]$proc.Name; $cmd=[string]$proc.CommandLine; $sig=($name + ' ' + $cmd).ToLowerInvariant(); $isDocker=$name -match '(?i)^(docker|docker desktop|com\\.docker.*|docker-proxy|vpnkit|vmmem|vmmemws|wslhost)\\.exe$' -or $cmd.ToLowerInvariant() -match 'docker desktop|com\\.docker|docker-proxy|vpnkit|moby'; $isWsl=$name -match '(?i)^wslrelay\.exe$' -or $cmd.ToLowerInvariant() -match '--vm-id|wslrelay'; if ($isDocker -or $isWsl) { continue }; if ($sig -match 'rezzerv|vite|node|npm') { Write-Host ('    Stopping old Rezzerv-like process PID ' + $owningPid + ' (' + $name + ') on port ' + $port + '...'); Stop-Process -Id $owningPid -Force -ErrorAction SilentlyContinue } }" ^
  "Start-Sleep -Seconds 1; $remaining = GetVersion $base; if ($remaining -and $remaining -ne $targetVersion) { Write-Host ('[ERROR] Port ' + $port + ' still serves old Rezzerv version ' + $remaining + ' after targeted cleanup.'); exit 24 } else { exit 0 }"
if %errorlevel% neq 0 exit /b 1
exit /b 0

:VerifyFrontendPorts
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$currentVersion='%REZZERV_VERSION%';" ^
  "$primaryUrl='http://localhost:%FRONTEND_PORT%';" ^
  "$staleUrl='http://localhost:%STALE_FRONTEND_PORT%';" ^
  "function GetVersion([string]$base) { try { $v = Invoke-RestMethod -Uri ($base + '/version.json') -TimeoutSec 3; if ($v.version) { return [string]$v.version } } catch {}; try { $resp = Invoke-WebRequest -Uri ($base + '/') -UseBasicParsing -TimeoutSec 3; $content=[string]$resp.Content; $m=[regex]::Match($content,'Rezzerv[^0-9]*([0-9]+\.[0-9]+\.[0-9]+)'); if ($m.Success) { return $m.Groups[1].Value }; if ($content -match 'Rezzerv') { return 'UI_CONFIRMED_NO_VERSION' } } catch {}; return '' }" ^
  "$primaryVersion = GetVersion $primaryUrl;" ^
  "if (-not $primaryVersion) { exit 21 }" ^
  "if ($primaryVersion -ne 'UI_CONFIRMED_NO_VERSION' -and $primaryVersion -ne $currentVersion) { Write-Host ('[ERROR] Active frontend on port %FRONTEND_PORT% serves version ' + $primaryVersion + ' instead of ' + $currentVersion + '.'); exit 23 }" ^
  "if ($primaryVersion -eq 'UI_CONFIRMED_NO_VERSION') { Write-Host ('[INFO] Active frontend on port %FRONTEND_PORT% serves Rezzerv UI, but no machine-detectable version string was found. Action: allow'); }" ^
  "$staleVersion = GetVersion $staleUrl;" ^
  "if (-not $staleVersion) { exit 0 }" ^
  "if ($staleVersion -eq 'UI_CONFIRMED_NO_VERSION') { Write-Host ('[INFO] Port %STALE_FRONTEND_PORT% is reachable and shows Rezzerv UI without detectable version. Action: warn only'); exit 0 }" ^
  "if ($staleVersion -eq $currentVersion) { Write-Host ('[INFO] Port %STALE_FRONTEND_PORT% mirrors current Rezzerv version ' + $staleVersion + '. Action: ignore'); exit 0 }" ^
  "Write-Host ('[ERROR] Port %STALE_FRONTEND_PORT% still serves old Rezzerv frontend version ' + $staleVersion + ' while target is ' + $currentVersion + '.'); exit 24"
if %errorlevel% neq 0 (
  if "%errorlevel%"=="21" echo [ERROR] Expected frontend port %FRONTEND_PORT% is not reachable.
  exit /b 1
)
echo     Active frontend verified on port %FRONTEND_PORT%. No stale Rezzerv frontend remains on port %STALE_FRONTEND_PORT%.
exit /b 0
