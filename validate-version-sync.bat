@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "EXPECTED="
if exist "VERSION.txt" (
  set /p EXPECTED=<VERSION.txt
)
if not defined EXPECTED (
  echo [ERROR] VERSION.txt ontbreekt of is leeg.
  exit /b 1
)

set "FILES=version.json backend\VERSION.txt frontend\version.json frontend\public\version.json frontend\package.json"
for %%F in (%FILES%) do (
  if not exist "%%~F" (
    echo [ERROR] Verplicht versiebestand ontbreekt: %%~F
    exit /b 2
  )
)

for %%F in (backend\VERSION.txt) do (
  set "RAW="
  set /p RAW=<"%%~F"
  if /I not "!RAW!"=="%EXPECTED%" (
    echo [ERROR] Versiemismatch in %%~F. Gevonden: !RAW! Verwacht: %EXPECTED%
    exit /b 3
  )
)

for %%F in (version.json frontend\version.json frontend\public\version.json) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$expected='%EXPECTED%'; $path='%%~F'; try { $json = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json -ErrorAction Stop; $actual = [string]$json.version } catch { Write-Host ('[ERROR] Kan versie niet lezen uit ' + $path); exit 4 }; if ($actual -ne $expected) { Write-Host ('[ERROR] Versiemismatch in ' + $path + '. Gevonden: ' + $actual + ' Verwacht: ' + $expected); exit 5 }" >nul
  if errorlevel 1 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$expected='%EXPECTED%'; $path='%%~F'; try { $json = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json -ErrorAction Stop; $actual = [string]$json.version; if ($actual -ne $expected) { Write-Host ('[ERROR] Versiemismatch in ' + $path + '. Gevonden: ' + $actual + ' Verwacht: ' + $expected); exit 5 } } catch { Write-Host ('[ERROR] Kan versie niet lezen uit ' + $path); exit 4 }"
    exit /b 5
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$expected='%EXPECTED%'; $path='frontend/package.json'; if ($expected -notmatch '(\d+)\.(\d+)\.(\d+)$') { Write-Host ('[ERROR] Kan packageversie niet afleiden uit ' + $expected); exit 6 }; $expectedPackage = $Matches[1] + '.' + $Matches[2] + '.' + $Matches[3]; try { $json = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json -ErrorAction Stop; $actual = [string]$json.version } catch { Write-Host ('[ERROR] Kan versie niet lezen uit ' + $path); exit 6 }; if ($actual -ne $expectedPackage) { Write-Host ('[ERROR] Versiemismatch in ' + $path + '. Gevonden: ' + $actual + ' Verwacht: ' + $expectedPackage); exit 6 }" 
if errorlevel 1 exit /b 6

if exist ".\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: .\rezzerv.db
  exit /b 7
)

if exist ".\backend\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: .\backend\rezzerv.db
  exit /b 8
)

echo [OK] Versiesync gecontroleerd: alle 5 verplichte versiebestanden staan op %EXPECTED% en verboden sqlite-bestanden ontbreken.
exit /b 0
