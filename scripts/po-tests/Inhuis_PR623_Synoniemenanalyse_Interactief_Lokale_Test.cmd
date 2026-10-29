@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion

rem Based on the proven local PO-test script for PR622; only PR, SHA, version and checks changed.
set "ROOT=%USERPROFILE%\Rezzerv_CODEX_WORK"
if exist "%CD%\start.bat" if exist "%CD%\docker-compose.yml" set "ROOT=%CD%"
set "BRANCH=codex/synoniemenanalyse-catalogus-overzicht"
set "VERSION=Rezzerv-MVP-v01.12.333"
set "EXPECTED=a68f31d5d7b981265e5789d8cd920986294f56a0"
set "REPORT=%USERPROFILE%\Downloads\Inhuis_PR623_Synoniemenanalyse_Interactief_Resultaat.txt"
set "STEP=Voorcontrole"
set "REASON=Onbekende reden"
set "STARTED=NEE"
set "RESULT=VEILIG GESTOPT"

if not exist "%USERPROFILE%\Downloads\" set "REPORT=%TEMP%\Inhuis_PR623_Synoniemenanalyse_Interactief_Resultaat.txt"
>"%REPORT%" echo INHUIS PR 623 - SYNONIEMENANALYSE - LOKALE TEST
>>"%REPORT%" echo Branch: %BRANCH%
>>"%REPORT%" echo Verwachte kandidaat: %EXPECTED%
>>"%REPORT%" echo Verwachte versie: %VERSION%
>>"%REPORT%" echo Geen reset, clean, stash, losse Docker-acties of databaseherstel.
>>"%REPORT%" echo LET OP: start.bat herbouwt en herstart lokale Inhuis-containers, voert noodzakelijke databasemigraties uit en kan de scanner starten.

set "STEP=1. Ontwikkelmap controleren"
if not exist "%ROOT%\" (
  set "REASON=De gebruikelijke ontwikkelmap ontbreekt."
  goto :fail
)
if not exist "%ROOT%\start.bat" (
  set "REASON=De officiele start.bat ontbreekt."
  goto :fail
)
if not exist "%ROOT%\docker-compose.yml" (
  set "REASON=De officiele docker-compose.yml ontbreekt."
  goto :fail
)

set "STEP=2. Git-repository controleren"
where git.exe >nul 2>nul
if errorlevel 1 (
  set "REASON=Git is niet beschikbaar."
  goto :fail
)
set "TOP="
for /f "usebackq delims=" %%G in (`git -C "%ROOT%" rev-parse --show-toplevel 2^>nul`) do set "TOP=%%G"
if not defined TOP (
  set "REASON=De ontwikkelmap is geen geldige Git-repository."
  goto :fail
)
set "TOP=%TOP:/=\%"
if /I not "%TOP%"=="%ROOT%" (
  set "REASON=De werkmap is niet de verwachte repository-root."
  goto :fail
)

set "STEP=3. Lokale wijzigingen beschermen"
git -C "%ROOT%" diff --quiet --exit-code
if errorlevel 1 (
  set "REASON=Er zijn lokale bronwijzigingen. Er is niets overschreven."
  goto :fail
)
git -C "%ROOT%" diff --cached --quiet --exit-code
if errorlevel 1 (
  set "REASON=Er zijn klaargezette bronwijzigingen. Er is niets overschreven."
  goto :fail
)
set "TRACKED="
for /f "usebackq delims=" %%S in (`git -C "%ROOT%" status --porcelain --untracked-files=no 2^>nul`) do set "TRACKED=JA"
if defined TRACKED (
  set "REASON=Git ziet bijgehouden wijzigingen. Veilig gestopt."
  goto :fail
)
>>"%REPORT%" echo Bijgehouden bestanden schoon; niet-gevolgde bestanden blijven behouden.

set "STEP=4. Alleen de bedoelde PR-branch ophalen"
git -C "%ROOT%" fetch --no-tags origin "+refs/heads/%BRANCH%:refs/remotes/origin/%BRANCH%"
if errorlevel 1 (
  set "REASON=De PR-branch kon niet worden opgehaald."
  goto :fail
)
set "REMOTE="
for /f "usebackq delims=" %%H in (`git -C "%ROOT%" rev-parse "refs/remotes/origin/%BRANCH%" 2^>nul`) do set "REMOTE=%%H"
>>"%REPORT%" echo GitHub-kandidaat: %REMOTE%
if /I not "%REMOTE%"=="%EXPECTED%" (
  set "REASON=De PR is veranderd. Vraag een nieuw exact-SHA-testscript."
  goto :fail
)

set "STEP=5. Testbranch veilig selecteren"
git -C "%ROOT%" show-ref --verify --quiet "refs/heads/%BRANCH%"
if errorlevel 1 goto :newbranch
git -C "%ROOT%" switch "%BRANCH%"
if errorlevel 1 (
  set "REASON=Omschakelen geblokkeerd; bestaande bestanden worden beschermd."
  goto :fail
)
git -C "%ROOT%" merge --ff-only "origin/%BRANCH%"
if errorlevel 1 (
  set "REASON=De bestaande lokale branch kan niet veilig worden bijgewerkt."
  goto :fail
)
goto :verify

:newbranch
git -C "%ROOT%" switch --track -c "%BRANCH%" "origin/%BRANCH%"
if errorlevel 1 (
  set "REASON=De testbranch kon niet veilig worden aangemaakt."
  goto :fail
)

:verify
set "STEP=6. Exacte branch en commit bevestigen"
set "ACTUALBRANCH="
set "LOCAL="
for /f "usebackq delims=" %%B in (`git -C "%ROOT%" branch --show-current 2^>nul`) do set "ACTUALBRANCH=%%B"
for /f "usebackq delims=" %%H in (`git -C "%ROOT%" rev-parse HEAD 2^>nul`) do set "LOCAL=%%H"
>>"%REPORT%" echo Lokale branch: %ACTUALBRANCH%
>>"%REPORT%" echo Lokale kandidaat: %LOCAL%
if not "%ACTUALBRANCH%"=="%BRANCH%" (
  set "REASON=De actieve branch klopt niet."
  goto :fail
)
if /I not "%LOCAL%"=="%EXPECTED%" (
  set "REASON=De lokale commit is niet de verwachte PR-kandidaat."
  goto :fail
)

set "STEP=7. Applicatieversie controleren"
set "LOCAL_VERSION="
if not exist "%ROOT%\VERSION.txt" (
  set "REASON=VERSION.txt ontbreekt."
  goto :fail
)
for /f "usebackq delims=" %%V in ("%ROOT%\VERSION.txt") do set "LOCAL_VERSION=%%V"
>>"%REPORT%" echo Lokale versie: %LOCAL_VERSION%
if /I not "%LOCAL_VERSION%"=="%VERSION%" (
  set "REASON=De lokale applicatieversie wijkt af."
  goto :fail
)

set "STEP=8. Officiele Inhuis-start"
>>"%REPORT%" echo Exacte kandidaat bevestigd; start.bat wordt aangeroepen.
echo.
echo De juiste kandidaat is geladen. Inhuis start via start.bat.
echo LET OP: dit herbouwt/herstart lokale containers en kan een database-migratie uitvoeren.
set "STARTED=JA"
pushd "%ROOT%"
call start.bat
set "STARTCODE=%ERRORLEVEL%"
popd
if not "%STARTCODE%"=="0" (
  set "REASON=De officiele start.bat meldde een fout. Geen automatisch herstel uitgevoerd."
  >>"%REPORT%" echo start.bat exitcode: %STARTCODE%
  goto :fail
)
>>"%REPORT%" echo start.bat exitcode: 0.
set "RESULT=KLAAR VOOR FUNCTIONELE TEST"
goto :end

:fail
>>"%REPORT%" echo VEILIG GESTOPT bij: %STEP%
>>"%REPORT%" echo Reden: %REASON%
>>"%REPORT%" echo start.bat aangeroepen: %STARTED%
>>"%REPORT%" echo Geen reset, clean, stash of eigen database-/Dockerherstel uitgevoerd.

:end
CLS
echo ==============================================================
echo     INHUIS PR 623 - SYNONIEMENANALYSE - LOKALE TEST
echo ==============================================================
echo Resultaat: %RESULT%
echo Laatste stap: %STEP%
if "%RESULT%"=="VEILIG GESTOPT" echo Reden: %REASON%
echo start.bat aangeroepen: %STARTED%
echo Rapport: %REPORT%
echo.
if "%RESULT%"=="VEILIG GESTOPT" goto :finish
echo Open http://localhost:5174 en meld je aan als Superuser of Frontteamlid.
echo Open Catalogus en klik op Synoniemenanalyse.
echo.
echo CONTROLE A: Vier tellers 0, 1, 2 en 3 of meer synoniemen.
echo CONTROLE B: Een teller aanklikken filtert de artikeltabel.
echo   Nogmaals dezelfde teller aanklikken toont weer alle artikelen.
echo CONTROLE C: Klik op een artikelnaam: maximaal 5 kandidaten eronder.
echo CONTROLE D: Een rondje selecteren schrijft nog niets.
echo CONTROLE E: Kies uitsluitend een werkelijk gelijkwaardig artikel.
echo   Klik op Merk kandidaat aan als synoniem om de relatie op te slaan.
echo CONTROLE F: Tellerwaarden en beide Catalogusartikelen veranderen.
echo CONTROLE G: Dubbelklikken op een ANDERE kandidaat slaat direct op.
echo   LET OP: dit wijzigt ECHTE lokale Catalogusrelaties.
echo CONTROLE H: Herhaal in een smal browservenster (mobiele weergave).
echo CONTROLE I: Reguliere gebruiker kan dit scherm niet openen.
echo.
echo Deel het rapport uit Downloads en eventuele schermafbeeldingen.

:finish
echo.
echo Dit venster blijft open totdat je op een toets drukt.
pause
endlocal
