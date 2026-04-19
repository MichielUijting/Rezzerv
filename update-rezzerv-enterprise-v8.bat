@echo off
setlocal EnableDelayedExpansion

:: ===============================
:: CONFIGURATIE
:: ===============================
set IMPORT_DIR=C:\Users\Gebruiker\Rezzerv-import
set REPO_DIR=C:\Users\Gebruiker\OneDrive\Scans\Documenten\GitHub\Rezzerv
set TEMP_DIR=C:\Users\Gebruiker\Rezzerv-temp
set BLOCKED_DB_ROOT=rezzerv.db
set BLOCKED_DB_BACKEND=backend\rezzerv.db
set REQUIRED_DB_DIR=backend\data
set REQUIRED_STARTBAT=start.bat
set REQUIRED_COMPOSE=docker-compose.yml
set REQUIRED_DBPY=backend\app\db.py

:: ===============================
:: HULPFUNCTIES
:: ===============================
set ROOT_ROBO_FLAGS=/E /NFL /NDL /NJH /NJS /XD ".git"
set MIRROR_ROBO_FLAGS=/MIR /NFL /NDL /NJH /NJS

echo.
echo === Rezzerv Auto Update Start ===
echo.

if not exist "%REPO_DIR%\.git" (
    echo FOUT: Geen geldige git repository in %REPO_DIR%
    pause
    exit /b 1
)

set ZIP_FILE=
for /f "delims=" %%i in ('dir "%IMPORT_DIR%\*.zip" /b /a-d /o-d') do (
    set ZIP_FILE=%%i
    goto :foundzip
)

:foundzip
if "%ZIP_FILE%"=="" (
    echo Geen ZIP gevonden in %IMPORT_DIR%
    pause
    exit /b 1
)

echo Nieuwste ZIP gevonden: %ZIP_FILE%

if exist "%TEMP_DIR%" rmdir /s /q "%TEMP_DIR%"
mkdir "%TEMP_DIR%"

powershell -NoProfile -Command "Expand-Archive -Path '%IMPORT_DIR%\%ZIP_FILE%' -DestinationPath '%TEMP_DIR%' -Force"
if errorlevel 1 (
    echo FOUT: Uitpakken van ZIP is mislukt.
    pause
    exit /b 1
)

set EXTRACT_ROOT=%TEMP_DIR%
if not exist "%EXTRACT_ROOT%\%REQUIRED_STARTBAT%" (
    for /d %%d in ("%TEMP_DIR%\*") do (
        if exist "%%~fd\%REQUIRED_STARTBAT%" (
            set EXTRACT_ROOT=%%~fd
            goto :rootfound
        )
    )
)

:rootfound
echo Geselecteerde ZIP-root: %EXTRACT_ROOT%

echo Runtime-structuur valideren...
if not exist "%EXTRACT_ROOT%\%REQUIRED_STARTBAT%" (
    echo FOUT: start.bat ontbreekt in ZIP.
    pause
    exit /b 1
)
if not exist "%EXTRACT_ROOT%\%REQUIRED_COMPOSE%" (
    echo FOUT: docker-compose.yml ontbreekt in ZIP.
    pause
    exit /b 1
)
if not exist "%EXTRACT_ROOT%\%REQUIRED_DBPY%" (
    echo FOUT: backend\app\db.py ontbreekt in ZIP.
    pause
    exit /b 1
)
if not exist "%EXTRACT_ROOT%\%REQUIRED_DB_DIR%" (
    echo FOUT: backend\data ontbreekt in ZIP. Runtime database-structuur ongeldig.
    pause
    exit /b 1
)

echo Verboden databasebestanden controleren...
if exist "%EXTRACT_ROOT%\%BLOCKED_DB_ROOT%" (
    echo FOUT: Verboden databasebestand gevonden in ZIP: %BLOCKED_DB_ROOT%
    pause
    exit /b 1
)
if exist "%EXTRACT_ROOT%\%BLOCKED_DB_BACKEND%" (
    echo FOUT: Verboden databasebestand gevonden in ZIP: %BLOCKED_DB_BACKEND%
    pause
    exit /b 1
)

echo start.bat controleren op verboden temp-runtime...
findstr /I /C:"rezzerv_build" "%EXTRACT_ROOT%\start.bat" >nul
if not errorlevel 1 (
    echo FOUT: start.bat gebruikt nog een tijdelijke buildmap ^(rezzerv_build^). Update geblokkeerd.
    pause
    exit /b 1
)
findstr /I /C:"robocopy \"%%cd%%\" \"%%BUILD_DIR%%\"" "%EXTRACT_ROOT%\start.bat" >nul
if not errorlevel 1 (
    echo FOUT: start.bat kopieert nog naar een buildmap. Update geblokkeerd.
    pause
    exit /b 1
)

if exist "%REPO_DIR%\VERSION.txt" (
    set /p CURRENT_VERSION=<"%REPO_DIR%\VERSION.txt"
) else (
    set CURRENT_VERSION=0
)

if exist "%EXTRACT_ROOT%\VERSION.txt" (
    set /p NEW_VERSION=<"%EXTRACT_ROOT%\VERSION.txt"
) else (
    echo Geen VERSION.txt gevonden in ZIP. Update geblokkeerd.
    pause
    exit /b 1
)

echo Huidige versie: !CURRENT_VERSION!
echo Nieuwe versie: !NEW_VERSION!

if "!NEW_VERSION!"=="!CURRENT_VERSION!" (
    echo Zelfde versie gedetecteerd. Update geblokkeerd.
    pause
    exit /b 1
)

echo Oude release-documenten opschonen in repo...
for %%f in (
    "Rezzerv-Validatierapport_v*.txt"
    "Rezzerv-PO-testinstructie_v*.txt"
    "Rezzerv-Packaging-Manifest_v*.txt"
    "VALIDATIERAPPORT_v*.txt"
    "PO-TESTINSTRUCTIE_v*.txt"
    "Opleveringsmanifest_v*.txt"
) do (
    del /q "%REPO_DIR%\%%~f" 2>nul
)

echo Verboden databasebestanden opschonen in repo...
if exist "%REPO_DIR%\rezzerv.db" del /q "%REPO_DIR%\rezzerv.db"
if exist "%REPO_DIR%\backend\rezzerv.db" del /q "%REPO_DIR%\backend\rezzerv.db"

echo Frontend en runtime caches opschonen in repo...
if exist "%REPO_DIR%\frontend\dist" rmdir /s /q "%REPO_DIR%\frontend\dist"
if exist "%REPO_DIR%\frontend\node_modules\.vite" rmdir /s /q "%REPO_DIR%\frontend\node_modules\.vite"
if exist "%REPO_DIR%\frontend\.vite" rmdir /s /q "%REPO_DIR%\frontend\.vite"
for /r "%REPO_DIR%" %%f in (*.pyc) do del /q "%%f" 2>nul
for /d /r "%REPO_DIR%" %%d in (__pycache__) do rmdir /s /q "%%d" 2>nul

echo Basisbestanden kopieren naar repo...
robocopy "%EXTRACT_ROOT%" "%REPO_DIR%" %ROOT_ROBO_FLAGS%
set ROBOCODE=%ERRORLEVEL%
if %ROBOCODE% GEQ 8 (
    echo FOUT: Basiskopie is mislukt met code %ROBOCODE%.
    pause
    exit /b %ROBOCODE%
)

if exist "%EXTRACT_ROOT%\frontend\dist" (
    echo Frontend dist spiegelen...
    robocopy "%EXTRACT_ROOT%\frontend\dist" "%REPO_DIR%\frontend\dist" %MIRROR_ROBO_FLAGS%
    set DISTROBOCODE=!ERRORLEVEL!
    if !DISTROBOCODE! GEQ 8 (
        echo FOUT: Frontend dist spiegeling is mislukt met code !DISTROBOCODE!.
        pause
        exit /b !DISTROBOCODE!
    )
) else (
    echo WAARSCHUWING: frontend\dist ontbreekt in de ZIP. Oude build is verwijderd; repo bevat nu geen frontend dist.
)

cd /d "%REPO_DIR%"
git add .
git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 (
    echo Eerste baseline commit maken...
    git commit -m "Initial baseline via BAT: %ZIP_FILE%"
    git branch -M main
    git push -u origin main
) else (
    git commit -m "Auto update via BAT: %ZIP_FILE%"
    git push origin main
)

if exist "%TEMP_DIR%\MILESTONE.txt" (
    for /f "delims=" %%t in (%TEMP_DIR%\MILESTONE.txt) do (
        set TAG_NAME=%%t
    )
    if not "!TAG_NAME!"=="" (
        echo Milestone tag detected: !TAG_NAME!
        git tag !TAG_NAME!
        git push origin !TAG_NAME!
        echo Milestone tag !TAG_NAME! aangemaakt en gepusht.
    )
)

echo.
echo === Update voltooid ===
echo Runtime-gates gecontroleerd: vaste databasebasis afgedwongen.
echo.
pause
