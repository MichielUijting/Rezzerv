@echo off
cd /d "%~dp0"
echo Sluit eerst het venster Start InHuis. Alle tijdelijke gegevens worden gewist.
set /p CONFIRM=Typ VERWIJDEREN om door te gaan: 
if not "%CONFIRM%"=="VERWIJDEREN" exit /b 1
"%~dp0runtime\python\python.exe" -c "from pathlib import Path; import shutil; p=Path('data').resolve(); root=Path.cwd().resolve(); assert p.parent==root and not p.is_symlink(); shutil.rmtree(p,ignore_errors=True)"
if errorlevel 1 (echo Opschonen mislukt. & pause & exit /b 1)
echo Tijdelijke gegevens verwijderd. Verwijder nu deze gehele InHuis-map.
pause
