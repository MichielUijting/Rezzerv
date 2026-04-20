@echo off
setlocal EnableExtensions EnableDelayedExpansion

git fetch --tags

if "%~1"=="" (
  for /f "usebackq delims=" %%v in ("VERSION.txt") do set "CURR=%%v"

  for /f "usebackq delims=" %%n in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$v = Get-Content 'VERSION.txt' -Raw;" ^
    "$v = $v.Trim();" ^
    "$match = [regex]::Match($v, '(.*?)(\d+)\.(\d+)\.(\d+)$');" ^
    "if (-not $match.Success) { throw 'Kan versie niet parsen.' }" ^
    "$prefix = $match.Groups[1].Value;" ^
    "$major = [int]$match.Groups[2].Value;" ^
    "$minor = [int]$match.Groups[3].Value;" ^
    "$patch = [int]$match.Groups[4].Value + 1;" ^
    "Write-Output ($prefix + $major + '.' + $minor + '.' + $patch)"`) do set "VERSION=%%n"
) else (
  set VERSION=%~1
)

echo ========================================
echo Rezzerv Release Flow
echo Version: %VERSION%
echo ========================================

call sync-version.bat %VERSION% || exit /b 1

powershell -ExecutionPolicy Bypass -Command ^
  "$lastTag = git describe --tags --abbrev=0 2>$null;" ^
  "$range = if ($lastTag) { $lastTag + '..HEAD' } else { 'HEAD' };" ^
  "$commits = git log $range --pretty=format:'- %s';" ^
  "$date = Get-Date -Format 'yyyy-MM-dd';" ^
  "$entry = \"`n## %VERSION% - $date`n$commits`n\";" ^
  "$content = Get-Content CHANGELOG.md -Raw;" ^
  "$new = $content -replace '# Changelog', '# Changelog' + $entry;" ^
  "Set-Content CHANGELOG.md $new"

git add .
git commit -m "release: %VERSION%"

git tag %VERSION%

git push origin HEAD
git push origin %VERSION%

echo ========================================
echo RELEASE COMPLETE: %VERSION%
echo ========================================

exit /b 0
