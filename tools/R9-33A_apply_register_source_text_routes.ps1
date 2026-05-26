$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-33A apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

path = Path('backend/app/main.py')
text = path.read_text(encoding='utf-8')

import_line = 'from app.testing_receipt_line_diagnosis_routes import install_receipt_line_diagnosis_routes\n'
if import_line not in text:
    anchor = 'from app.services.receipt_status_baseline_service import diagnose_receipt_status_baseline, validate_receipt_status_baseline\n'
    if anchor not in text:
        raise SystemExit('R9-33A import anchor not found')
    text = text.replace(anchor, anchor + import_line, 1)

install_line = 'install_receipt_line_diagnosis_routes(app, engine)\n'
if install_line not in text:
    anchor = 'app.include_router(receipt_import_diagnosis_router)\n'
    if anchor not in text:
        raise SystemExit('R9-33A router anchor not found')
    text = text.replace(anchor, anchor + install_line, 1)

path.write_text(text, encoding='utf-8')
print('R9-33A applied: receipt source text routes registered at startup')
'@

$py | python -

git --no-pager diff -- backend/app/main.py

git add backend/app/main.py
git commit -m 'R9-33A register receipt source text routes at startup'
git push

Write-Host 'R9-33A toegepast en gepusht.'
