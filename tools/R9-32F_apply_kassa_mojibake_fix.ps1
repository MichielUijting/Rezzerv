$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32F apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path

paths = [
    Path('frontend/src/features/receipts/KassaPage.jsx'),
]

replacements = {
    'â€¦': '...',
    'â€˜': "'",
    'â€™': "'",
    'â€œ': '"',
    'â€\u009d': '"',
    'â€“': '-',
    'â€”': '-',
    'Â ': ' ',
    'Â': '',
}

changed = []
for path in paths:
    text = path.read_text(encoding='utf-8')
    original = text
    for old, new in replacements.items():
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding='utf-8')
        changed.append(str(path))

if changed:
    print('R9-32F applied to:')
    for item in changed:
        print('-', item)
else:
    print('R9-32F: no mojibake patterns found')
'@

$py | python -

git --no-pager diff -- frontend/src/features/receipts/KassaPage.jsx

git add frontend/src/features/receipts/KassaPage.jsx
git commit -m 'R9-32F fix Kassa upload mojibake labels'
git push

Write-Host 'R9-32F toegepast en gepusht.'
