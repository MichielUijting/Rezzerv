@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo Rezzerv Productcatalogus Release A Check
echo ========================================
python product_catalog_release_a_check.py rezzerv.db
if errorlevel 1 (
  echo.
  echo [FOUT] Productcatalogus validatie bevat rode punten.
) else (
  echo.
  echo [OK] Productcatalogus Release A validatie geslaagd.
)
pause
