@echo off
CLS
setlocal EnableExtensions DisableDelayedExpansion
set "BASE=%~dp0"
if not exist "%BASE%Inhuis-Server-Voorcontrole.ps1" (
  CLS
  echo INHUIS - SERVER VOORCONTROLE
  echo NIET UITGEVOERD: het officiële controlescript ontbreekt naast dit bestand.
  echo Er is niets gewijzigd.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%BASE%Inhuis-Server-Voorcontrole.ps1"
set "RC=%ERRORLEVEL%"
CLS
echo INHUIS - SERVER VOORCONTROLE
if not "%RC%"=="0" (
  echo De inventarisatie is niet volledig bevestigd. Foutcode %RC%.
  echo Er is geen Docker- of databaseactie uitgevoerd door dit script.
) else (
  echo Controle afgerond. Lees het rapport in Downloads.
  echo Dit is GEEN toestemming voor herstart of upgrade.
)
echo.
pause
exit /b %RC%
