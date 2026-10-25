@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
rem READ ONLY: no Docker/Windows/Git changes. Never print container environment/secrets.
set "REPORT_DIR=%USERPROFILE%\Downloads"
if not exist "%REPORT_DIR%" set "REPORT_DIR=%TEMP%"
set "REPORT=%REPORT_DIR%\Inhuis_Server_Beheer_Voorcontrole_Resultaat.txt"
set "TMP_REPORT=%TEMP%\Inhuis_Server_Beheer_Voorcontrole_%RANDOM%%RANDOM%.tmp"
set "RESULT=ONVOLLEDIG"

>"%TMP_REPORT%" echo INHUIS - SERVERBEHEER VOORCONTROLE - ALLEEN LEZEN
>>"%TMP_REPORT%" echo Datum: %DATE% %TIME%
>>"%TMP_REPORT%" echo Geen Windows-update, herstart, containerwijziging of deployment uitgevoerd.
>>"%TMP_REPORT%" echo.

where docker.exe >nul 2>&1
if errorlevel 1 (
  >>"%TMP_REPORT%" echo BLOKKADE: Docker CLI niet gevonden.
  goto :finish
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
  >>"%TMP_REPORT%" echo BLOKKADE: Windows PowerShell niet gevonden.
  goto :finish
)
docker version --format "Docker client={{.Client.Version}}; engine={{.Server.Version}}" >>"%TMP_REPORT%" 2>nul
if errorlevel 1 (
  >>"%TMP_REPORT%" echo BLOKKADE: Docker-engine niet bereikbaar. Geen herstel geprobeerd.
  goto :finish
)
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Docker-containers: naam, image, status en restartbeleid]
rem Image IDs and labels help identify candidates; they never prove database authority.
docker ps -a --format "naam={{.Names}} ; image={{.Image}} ; status={{.Status}}" >>"%TMP_REPORT%" 2>nul
if errorlevel 1 (
  >>"%TMP_REPORT%" echo BLOKKADE: Containerinventaris niet beschikbaar.
  goto :finish
)
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Restartbeleid en image-identiteit van alle containers]
docker ps -aq | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { $id=$_.Trim(); if($id){ docker.exe inspect --format 'naam={{.Name}} restart={{.HostConfig.RestartPolicy.Name}} imageID={{.Image}}' $id 2>$null } }" >>"%TMP_REPORT%" 2>nul
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Windows-aanmeldstart: alleen taaknamen en status]
powershell.exe -NoProfile -NonInteractive -Command "Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'Inhuis|Docker|Scanner' } | Select-Object TaskName,State | Format-Table -HideTableHeaders | Out-String -Width 160" >>"%TMP_REPORT%" 2>nul
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Windows automatische start via gebruikersaccount]
powershell.exe -NoProfile -NonInteractive -Command "Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Docker|Inhuis' } | ForEach-Object { $_.Name }" >>"%TMP_REPORT%" 2>nul
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Lokale bereikbaarheidscontrole; geen gebruikersaanmelding]
powershell.exe -NoProfile -NonInteractive -Command "foreach($u in @('http://127.0.0.1:8011/api/health','http://127.0.0.1:5174/','http://127.0.0.1:8003/health')){ try { $r=Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 4; Write-Output ($u+' : HTTP '+[int]$r.StatusCode) } catch { Write-Output ($u+' : niet bereikbaar / afwijkend') } }" >>"%TMP_REPORT%" 2>nul
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo [Belangrijk]
>>"%TMP_REPORT%" echo Deze inventaris identificeert NIET zelfstandig de actieve database of veilige herstelroute.
>>"%TMP_REPORT%" echo Bewijs van volume-ID, PostgreSQL-cluster/schema en recente gebruikersdata is apart vereist.
>>"%TMP_REPORT%" echo Automatisch opstarten na reboot en externe mobiele toegang zijn hiermee NIET bewezen.
set "RESULT=DIAGNOSE UITGEVOERD - nog geen GO voor Windows-herstart"

:finish
>>"%TMP_REPORT%" echo.
>>"%TMP_REPORT%" echo Resultaat: %RESULT%
copy /Y "%TMP_REPORT%" "%REPORT%" >nul 2>&1
del /Q "%TMP_REPORT%" >nul 2>&1
CLS
echo ============================================================
echo INHUIS - SERVERBEHEER VOORCONTROLE
echo ============================================================
echo %RESULT%
echo.
echo Deel uitsluitend het TXT-rapport. Geen onderhoud uitgevoerd.
echo Rapport: %REPORT%
echo.
pause
endlocal
