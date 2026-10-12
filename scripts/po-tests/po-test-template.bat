@echo off
CLS
setlocal EnableExtensions EnableDelayedExpansion

rem Canonieke PO-start, afgeleid van bewezen PR544-batchscript.
rem Alleen generator-plaatshouders zijn toegestaan voor kandidaatgegevens.
set "REPO=%USERPROFILE%\Rezzerv_CODEX_WORK"
set "BRANCH=@@BRANCH@@"
set "EXPECTED_SHA=@@SHA@@"
set "APP_URL=http://localhost:5174"
set "TITLE=@@TITLE@@"
set "REPORT=%USERPROFILE%\Downloads\Inhuis_PO_Test_Resultaat.txt"
set "PHASE=Voorbereiding"
set "START_CALLED=NEE"
set "LOCAL_SHA=onbekend"

if not exist "%REPO%\.git" (
    set "WHY=De gekozen map bevat geen Git-repository."
    goto FAIL
)
if not exist "%REPO%\start.bat" (
    set "WHY=De officiele start.bat ontbreekt."
    goto FAIL
)
cd /d "%REPO%"
if errorlevel 1 (
    set "WHY=De repositorymap kon niet worden geopend."
    goto FAIL
)

set "PHASE=Git repository identiteit"
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    set "WHY=Git kan de repository niet lezen."
    goto FAIL
)
for /f "delims=" %%A in ('git rev-parse --show-prefix 2^>nul') do set "PREFIX=%%A"
if defined PREFIX (
    set "WHY=De opdracht wordt niet vanuit de repository-root uitgevoerd."
    goto FAIL
)
git remote get-url origin 2>nul | findstr /I /C:"MichielUijting/Rezzerv" >nul
if errorlevel 1 (
    set "WHY=De origin-repository is niet MichielUijting/Rezzerv."
    goto FAIL
)

set "PHASE=Lokale wijzigingen"
set "DIRTY="
for /f "delims=" %%A in ('git status --porcelain --untracked-files=no 2^>nul') do set "DIRTY=JA"
if errorlevel 1 (
    set "WHY=Git kon de werkmapstatus niet betrouwbaar vaststellen."
    goto FAIL
)
if defined DIRTY (
    set "WHY=Er zijn lokale wijzigingen. Bestaand werk wordt niet overschreven."
    goto FAIL
)
rem Untracked artefacten worden niet verwijderd. Git switch/merge weigeren
rem automatisch wanneer een ervan een bestand op de doelbranch zou overschrijven.

set "PHASE=Alleen taakbranch ophalen"
git fetch --no-tags origin "refs/heads/%BRANCH%:refs/remotes/origin/%BRANCH%"
if errorlevel 1 (
    set "WHY=Ophalen van de bedoelde GitHub-branch is mislukt."
    goto FAIL
)

set "PHASE=Remote kandidaat controleren"
set "REMOTE_SHA="
for /f "delims=" %%A in ('git rev-parse "refs/remotes/origin/%BRANCH%" 2^>nul') do set "REMOTE_SHA=%%A"
if /I not "!REMOTE_SHA!"=="%EXPECTED_SHA%" (
    set "WHY=Remote branch wijkt af van de verwachte commit."
    goto FAIL
)

set "PHASE=Branch veilig activeren"
git show-ref --verify --quiet "refs/heads/%BRANCH%"
if errorlevel 1 (
    git switch --track -c "%BRANCH%" "origin/%BRANCH%"
) else (
    git switch "%BRANCH%"
)
if errorlevel 1 (
    set "WHY=Branchwissel werd door Git geweigerd; lokale bestanden blijven behouden."
    goto FAIL
)
git merge --ff-only "origin/%BRANCH%"
if errorlevel 1 (
    set "WHY=Fast-forward update mislukt. Geen reset uitgevoerd."
    goto FAIL
)

set "PHASE=Lokale kandidaat controleren"
for /f "delims=" %%A in ('git rev-parse HEAD 2^>nul') do set "LOCAL_SHA=%%A"
if /I not "!LOCAL_SHA!"=="%EXPECTED_SHA%" (
    set "WHY=Lokale commit wijkt af van de verwachte commit."
    goto FAIL
)

CLS
echo ============================================================
echo INHUIS - %TITLE%
echo ============================================================
echo.
echo Branch: %BRANCH%
echo Commit: %EXPECTED_SHA%
echo.
echo De juiste kandidaat is gecontroleerd. Officiele start.bat wordt gestart.
echo.
set "PHASE=Officiele applicatiestart"
set "START_CALLED=JA"
call start.bat
if errorlevel 1 (
    set "WHY=De officiele start.bat meldde een fout."
    goto FAIL
)

CLS
echo ============================================================
echo INHUIS - KLAAR VOOR FUNCTIONELE TEST
echo ============================================================
echo Versie: %EXPECTED_SHA%
echo Open: %APP_URL%
echo.
echo @@TEST_INSTRUCTIONS@@
echo.
echo Rapport: %REPORT%
> "%REPORT%" (
    echo GESLAAGD: Inhuis gestart via de officiele start.bat.
    echo Branch: %BRANCH%
    echo SHA: %EXPECTED_SHA%
    echo start.bat aangeroepen: JA
)
pause
exit /b 0

:FAIL
CLS
echo ============================================================
echo INHUIS - VEILIG GESTOPT
echo ============================================================
echo Stap: %PHASE%
echo Reden: !WHY!
echo Branch: %BRANCH%
echo Verwachte SHA: %EXPECTED_SHA%
echo start.bat aangeroepen: %START_CALLED%
echo Geen destructieve Git-reset of eigen Docker-actie uitgevoerd.
if not exist "%USERPROFILE%\Downloads" mkdir "%USERPROFILE%\Downloads" >nul 2>&1
> "%REPORT%" (
    echo VEILIG GESTOPT
    echo Stap: %PHASE%
    echo Reden: !WHY!
    echo Branch: %BRANCH%
    echo Verwachte SHA: %EXPECTED_SHA%
    echo Remote SHA: !REMOTE_SHA!
    echo Lokale SHA: !LOCAL_SHA!
    echo start.bat aangeroepen: %START_CALLED%
)
echo Rapport: %REPORT%
pause
exit /b 1
