@echo off
CLS
setlocal

title Inhuis - Alternatieve kassabonscanner

set "ROOT=%~dp0"
set "SCANNER=%ROOT%external\in-huis-demo"
set "PYTHON=%SCANNER%\venv\Scripts\python.exe"
set "SCANNERENV=%SCANNER%\.env"
set "CONFIG=%ROOT%tools\receipt_scanner\configure_local_inhuis_demo.py"
set "BRIDGE=%ROOT%tools\receipt_scanner\inhuis_demo_bridge.py"

if not exist "%SCANNER%" goto :missing_scanner
if not exist "%PYTHON%" goto :missing_python
if not exist "%SCANNERENV%" goto :missing_env
if not exist "%CONFIG%" goto :missing_repo_file
if not exist "%BRIDGE%" goto :missing_repo_file

"%PYTHON%" "%CONFIG%"
if errorlevel 1 goto :config_error

rem Controleer poort 8003 fail-closed en parse /health als JSON.
rem Exitcodes: 0 = actuele bridge, 10 = oudere Inhuis-bridge,
rem 20 = onbekende listener/ongeldige health, 30 = geen listener.
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $c=Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 30}; try {$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8003/health' -TimeoutSec 2} catch {exit 20}; if(([string]$r.provider -eq 'in-huis-demo') -and ([int]$r.bridge_version -ge 2) -and ($r.capabilities.live_corner_detection -eq $true)){exit 0}; if([string]$r.provider -eq 'in-huis-demo'){exit 10}; exit 20" >nul 2>&1
set "HEALTH_STATUS=%ERRORLEVEL%"

if "%HEALTH_STATUS%"=="0" goto :already_current
if "%HEALTH_STATUS%"=="30" goto :start_bridge
if "%HEALTH_STATUS%"=="10" (
  powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $c=Get-NetTCPConnection -LocalPort 8003 -State Listen | Select-Object -First 1; if(-not $c){exit 2}; $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); if(($p.CommandLine -as [string]) -notmatch 'inhuis_demo_bridge\.py'){exit 3}; Stop-Process -Id $c.OwningProcess -Force; Start-Sleep -Milliseconds 750"
  if errorlevel 1 goto :port_in_use
  goto :start_bridge
)
goto :port_in_use

:already_current
rem De actuele AI-scanner draait al. Sluit direct zodat een opstartscript
rem geen extra blijvend PowerShell/cmd-venster achterlaat.
exit /b 0

:start_bridge
CLS
echo ============================================================
echo INHUIS - ALTERNATIEVE KASSABONSCANNER
echo ============================================================
echo.
echo De scanner-engine wordt als achtergrondservice gestart.
echo Er wordt GEEN apart inlog- of startscherm geopend.
echo.
echo Gebruik daarna alleen de normale Inhuis-interface.
echo De reguliere Inhuis-opstartroute blijft start.bat.
echo.
echo Dit venster moet open blijven zolang de scanner wordt gebruikt.
echo Stoppen kan met Ctrl+C.
echo ============================================================
echo.

"%PYTHON%" "%BRIDGE%"
set "EXITCODE=%ERRORLEVEL%"

CLS
echo ============================================================
echo INHUIS - ALTERNATIEVE KASSABONSCANNER GESTOPT
echo ============================================================
echo.
if "%EXITCODE%"=="0" (
  echo De scanner is gestopt.
) else (
  echo De scanner is onverwacht gestopt met foutcode %EXITCODE%.
)
echo.
pause
exit /b %EXITCODE%

:missing_scanner
CLS
echo ============================================================
echo INHUIS - SCANNERBRON ONTBREEKT
echo ============================================================
echo.
echo Verwacht:
echo %SCANNER%
echo.
echo De externe in-huis-demo repository moet daar aanwezig zijn.
echo.
pause
exit /b 1

:missing_python
CLS
echo ============================================================
echo INHUIS - PYTHONOMGEVING ONTBREEKT
echo ============================================================
echo.
echo Verwacht:
echo %PYTHON%
echo.
echo Installeer eerst de scanneromgeving.
echo.
pause
exit /b 1

:missing_env
CLS
echo ============================================================
echo INHUIS - SCANNERCONFIGURATIE ONTBREEKT
echo ============================================================
echo.
echo Verwacht:
echo %SCANNERENV%
echo.
echo Plaats de Anthropic API-key eerst in het lokale .env-bestand.
echo.
pause
exit /b 1

:missing_repo_file
CLS
echo ============================================================
echo INHUIS - REPOSITORYBESTAND ONTBREEKT
echo ============================================================
echo.
echo Werk de PR-branch eerst bij voordat je deze route gebruikt.
echo.
pause
exit /b 1

:config_error
CLS
echo ============================================================
echo INHUIS - LOKALE SCANNERCONFIGURATIE MISLUKT
echo ============================================================
echo.
echo De bestaande lokale configuratie is niet verwijderd.
echo.
pause
exit /b 1

:port_in_use
CLS
echo ============================================================
echo INHUIS - POORT 8003 IS AL IN GEBRUIK
echo ============================================================
echo.
echo Er draait iets op poort 8003, maar het script kan niet veilig
echo bevestigen dat dit de oude Inhuis AI-scanner is.
echo.
echo Er is daarom geen proces gestopt en niets gewijzigd.
echo.
pause
exit /b 1
