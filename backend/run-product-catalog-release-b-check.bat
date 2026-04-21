@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo ========================================
echo Rezzerv Product Catalog Release B Check
echo ========================================
"%PYTHON_EXE%" product_catalog_release_b_check.py "%~dp0rezzerv.db"
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] Release B controle heeft fouten gevonden.
  pause
  exit /b %EXIT_CODE%
)
echo [OK] Release B controle geslaagd.
pause
exit /b 0
