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

rem Controleer of poort 8003 al door een oudere Inhuis-bridge wordt gebruikt.
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "$ErrorActionPreference='SilentlyContinue'; try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8003/health).Content } catch { '' }"`) do set "EXISTING_HEALTH=%%H"

if defined EXISTING_HEALTH (
  echo %EXISTING_HEALTH% | findstr /C:"\"bridge_version\":2" >nul 2>&1
  if not errorlevel 1 goto :already_current

  echo %EXISTING_HEALTH% | findstr /C:"\"provider\":\"in-huis-demo\"" >nul 2>&1
  if not errorlevel 1 (
    powershell -NoProfile -Command "$ErrorActionPreference='Stop'; $c=Get-NetTCPConnection -LocalPort 8003 -State Listen | Select-Object -First 1; if(-not $c){exit 2}; $p=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $c.OwningProcess); if(($p.CommandLine -as [string]) -notmatch 'inhuis_demo_bridge\.py'){exit 3}; Stop-Process -Id $c.OwningProcess -Force; Start-Sleep -Milliseconds 750"
    if errorlevel 1 goto :port_in_use
  ) else (
    goto :port_in_use
  )
)

goto :start_bridge

:already_current
CLS
echo ============================================================
echo INHUIS - AI KASSABONSCANNER DRAAIT AL
echo ============================================================
echo.
echo De actuele scanner met live bonranddetectie draait al op poort 8003.
echo Er wordt geen tweede scannerproces gestart.
echo.
echo Laat het bestaande scannervenster open en gebruik Inhuis.
echo.
pause
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
