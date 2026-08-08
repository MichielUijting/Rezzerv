CLS
@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Rezzerv - Household Article Identity Slice 2B1 DRY-RUN
echo ============================================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo FOUT: Docker is niet beschikbaar.
  pause
  exit /b 1
)

echo [1/3] Backendservice en runtime-database controleren...
docker compose exec -T backend python -c "from app.db import get_runtime_datastore_info; import json; info=get_runtime_datastore_info(); print(json.dumps(info, ensure_ascii=False)); assert info.get('datastore') == 'sqlite'; assert info.get('database') == '/app/data/rezzerv.db'"
if errorlevel 1 (
  echo.
  echo FOUT: De backendservice is niet bereikbaar of de runtime-database wijkt af van /app/data/rezzerv.db.
  echo DRY-RUN GEBLOKKEERD.
  pause
  exit /b 2
)

echo.
echo [2/3] Controleren dat hostbestand backend\data\rezzerv.db bestaat...
if not exist "backend\data\rezzerv.db" (
  echo FOUT: backend\data\rezzerv.db ontbreekt. DRY-RUN GEBLOKKEERD.
  pause
  exit /b 3
)

echo.
echo [3/3] Slice 2B1 dry-run uitvoeren - GEEN databasewijzigingen...
echo.
docker compose exec -T backend python -m app.cli.migrate_household_article_identities
set RESULT=%ERRORLEVEL%

echo.
if "%RESULT%"=="0" (
  echo RESULTAAT: DRY-RUN GROEN - geen ambigue of onopgeloste referenties.
) else if "%RESULT%"=="2" (
  echo RESULTAAT: DRY-RUN STOP - ambigue en/of onopgeloste referenties gevonden.
  echo Er is niets gemigreerd; eerst beoordeling vereist.
) else (
  echo RESULTAAT: DRY-RUN TECHNISCH MISLUKT met exitcode %RESULT%.
)

echo.
echo LET OP: dit script gebruikt bewust GEEN --apply en wijzigt dus geen artikelidentiteiten.
pause
exit /b %RESULT%
