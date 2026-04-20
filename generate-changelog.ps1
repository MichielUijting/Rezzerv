param (
    [string]$Version
)

$lastTag = git describe --tags --abbrev=0 2>$null

if (-not $lastTag) {
    $commits = git log --pretty=format:"- %s"
} else {
    $commits = git log "$lastTag"..HEAD --pretty=format:"- %s"
}

$date = Get-Date -Format "yyyy-MM-dd"

$entry = "`n## $Version - $date`n$commits`n"

$content = Get-Content CHANGELOG.md -Raw
$newContent = $content -replace "# Changelog", "# Changelog`n$entry"

Set-Content CHANGELOG.md $newContent

Write-Host "[OK] Changelog bijgewerkt voor $Version"
