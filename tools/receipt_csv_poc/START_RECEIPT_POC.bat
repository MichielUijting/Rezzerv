@echo off
setlocal

cd /d %~dp0

echo ==============================================
echo Rezzerv Receipt OCR POC
echo ==============================================
echo.

if not exist input_receipts mkdir input_receipts
if not exist output_csv mkdir output_csv

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

python receipt_to_csv.py --input input_receipts --output output_csv --lang eng

echo.
echo ==============================================
echo Gereed.
echo Output map:
echo %~dp0output_csv
echo ==============================================
echo.
pause
