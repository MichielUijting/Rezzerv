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

if exist ".\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: .\rezzerv.db
  exit /b 6
)

if exist ".\backend\rezzerv.db" (
  echo [ERROR] Verboden databasebestand gevonden: .\backend\rezzerv.db
  exit /b 7
)

echo [OK] Versiesync gecontroleerd: alle 5 verplichte versiebestanden staan op %EXPECTED% en verboden sqlite-bestanden ontbreken.
exit /b 0
for %%F in (frontend\package.json) do (
  for /f "usebackq tokens=2 delims=:," " %%v in (`findstr /i /c:""version"" "%%~F"`) do (
    if not "%%~v"=="%EXPECTED%" (
      echo [ERROR] %%~F bevat %%~v in plaats van %EXPECTED%.
      set "FAIL=1"
    ) else (
      echo [OK] %%~F = %EXPECTED%
    )
  )
)

