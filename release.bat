@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Fetch latest tags
git fetch --tags

if "%1"=="" (
  for /f "tokens=1-3 delims=." %%a in ('git describe --tags --abbrev=0 2^>nul') do (
    set MAJOR=%%a
    set MINOR=%%b
    set PATCH=%%c
  )

  if not defined PATCH (
    set VERSION=01.13.00
  ) else (
    set /a PATCH+=1
    set VERSION=%MAJOR%.%MINOR%.%PATCH%
  )
) else (
  set VERSION=%1
)

echo ========================================
echo Rezzerv Release Flow
echo Version: %VERSION%
echo ========================================

REM Sync version
call sync-version.bat %VERSION% || exit /b 1

REM Generate changelog
powershell -ExecutionPolicy Bypass -File generate-changelog.ps1 -Version %VERSION%

REM Commit
git add .
git commit -m "release: %VERSION%"

REM Tag
git tag Rezzerv-v%VERSION%

REM Push
git push origin main
git push origin Rezzerv-v%VERSION%

echo ========================================
echo RELEASE COMPLETE: %VERSION%
echo ========================================

exit /b 0
