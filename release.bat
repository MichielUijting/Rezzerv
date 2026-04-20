@echo off
setlocal EnableExtensions EnableDelayedExpansion

if "%1"=="" (
  echo Usage: release.bat 01.13.00
  exit /b 1
)

set VERSION=%1

echo ========================================
echo Rezzerv Release Flow
echo Version: %VERSION%
echo ========================================

REM Step 1: sync version
call sync-version.bat %VERSION% || exit /b 1

REM Step 2: validate git state
git status --porcelain > temp_git_status.txt
for /f %%i in (temp_git_status.txt) do (
  set DIRTY=1
)
del temp_git_status.txt

if defined DIRTY (
  echo [INFO] Changes detected, continuing...
)

REM Step 3: commit changes
git add .
git commit -m "release: %VERSION%"

REM Step 4: create tag
git tag Rezzerv-v%VERSION%

REM Step 5: push everything
git push origin main
git push origin Rezzerv-v%VERSION%

echo ========================================
echo RELEASE COMPLETE: %VERSION%
echo ========================================

exit /b 0
