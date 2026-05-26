$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32G apply failed: verkeerde branch: $branch"
  exit 1
}

python .\tools\R9-32G_patch.py

git --no-pager diff -- backend/app/services/receipt_service.py

git add backend/app/services/receipt_service.py
git commit -m 'R9-32G merge positive contributors into receipt main flow'
git push

Write-Host 'R9-32G toegepast en gepusht.'
