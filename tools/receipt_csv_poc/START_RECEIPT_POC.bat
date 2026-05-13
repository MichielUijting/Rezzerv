@echo off
setlocal

cd /d %~dp0

echo ==============================================
echo Rezzerv Receipt OCR POC
echo ==============================================
echo.

if not exist input_receipts mkdir input_receipts
if not exist test_runs mkdir test_runs

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set RUN_ID=%%i
set OUTPUT_DIR=test_runs\run_%RUN_ID%
mkdir "%OUTPUT_DIR%"

echo [INFO] Deze run wordt opgeslagen in:
echo %~dp0%OUTPUT_DIR%
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is niet gevonden.
  echo Installeer Python 3.11+ en probeer opnieuw.
  pause
  exit /b 1
)

if not exist .venv (
  echo [INFO] Aanmaken virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [INFO] Installeren/updaten dependencies...
python -m pip install -r requirements.txt

echo.
echo [INFO] Start OCR verwerking...
echo.

python receipt_to_csv.py --input input_receipts --output "%OUTPUT_DIR%" --lang eng

echo.
echo ==============================================
echo Gereed.
echo Output map:
echo %~dp0%OUTPUT_DIR%
echo ==============================================
echo.
pause
