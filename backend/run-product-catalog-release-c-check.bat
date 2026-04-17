@echo off
setlocal
cd /d "%~dp0"
python product_catalog_release_c_check.py rezzerv.db
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo [ERROR] Release C productcataloguscheck is niet groen.
  pause
  exit /b %ERR%
)
echo.
echo [OK] Release C productcataloguscheck geslaagd.
pause
exit /b 0
