@echo off
CLS
setlocal EnableExtensions
set "ROOT=%~dp0"
set "SCANNER=%ROOT%tools\receipt_scanner\meesdeboer_engine"
set "VENV=%ROOT%tools\receipt_scanner\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "BRIDGE=%ROOT%tools\receipt_scanner\inhuis_demo_bridge.py"
set "CONFIG=%ROOT%tools\receipt_scanner\configure_local_inhuis_demo.py"
if not exist "%SCANNER%\scan_engine.py" goto :source_missing
if not exist "%SCANNER%\requirements.txt" goto :source_missing
if not exist "%BRIDGE%" goto :source_missing
if not exist "%CONFIG%" goto :source_missing
if not exist "%PYTHON%" goto :create_venv
:setup
rem Repair incomplete existing venvs without touching unrelated environments.
"%PYTHON%" -c "import onnxruntime, capybara, docaligner, anthropic, flask" >nul 2>&1
if errorlevel 1 (
  echo INHUIS - Ontbrekende scannerpakketten worden aangevuld.
  "%PYTHON%" -m pip install --disable-pip-version-check -r "%SCANNER%\requirements.txt"
  if errorlevel 1 goto :error
  "%PYTHON%" -c "import onnxruntime, capybara, docaligner, anthropic, flask" >nul 2>&1
  if errorlevel 1 goto :error
)
"%PYTHON%" "%CONFIG%"
if errorlevel 1 goto :error
rem Fail closed if any unknown listener owns scanner port; never kill processes.
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8003 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if(-not $c){exit 30}; try {$r=Invoke-RestMethod -Uri 'http://127.0.0.1:8003/health' -TimeoutSec 3} catch {exit 20}; if([string]$r.provider -eq 'in-huis-demo' -and [int]$r.bridge_version -ge 3){exit 0}; exit 20" >nul 2>&1
set "STATUS=%ERRORLEVEL%"
if "%STATUS%"=="0" exit /b 0
if not "%STATUS%"=="30" goto :port_in_use
CLS
echo ============================================================
echo INHUIS - EIGEN AI-KASSABONSCANNER
 echo ============================================================
echo De scanner draait uit jouw eigen Inhuis-broncode.
echo Dit venster open laten zolang je scant.
"%PYTHON%" "%BRIDGE%"
set "RESULT=%ERRORLEVEL%"
CLS
echo INHUIS - AI-SCANNER GESTOPT (code %RESULT%).
pause
exit /b %RESULT%
:create_venv
CLS
echo INHUIS - Eigen scanneromgeving eenmalig opbouwen.
where py >nul 2>&1
if not errorlevel 1 (py -3 -m venv "%VENV%") else (python -m venv "%VENV%")
if errorlevel 1 goto :error
"%PYTHON%" -m pip install --disable-pip-version-check -r "%SCANNER%\requirements.txt"
if errorlevel 1 goto :error
goto :setup
:source_missing
CLS
echo INHUIS - De scannerbron uit jouw repository ontbreekt.
pause
exit /b 1
:port_in_use
CLS
echo INHUIS - Poort 8003 is bezet door een onbekende of oudere scanner.
echo Er wordt geen bestaand proces gestopt. Sluit de oude scanner eerst veilig.
pause
exit /b 1
:error
CLS
echo INHUIS - Scannerconfiguratie of installatie is mislukt.
echo Bestaande Docker-containers en data zijn niet gewijzigd.
pause
exit /b 1