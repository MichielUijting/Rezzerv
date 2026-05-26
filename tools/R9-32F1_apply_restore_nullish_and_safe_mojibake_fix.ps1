$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32F1 apply failed: verkeerde branch: $branch"
  exit 1
}

$py = @'
from pathlib import Path
import re

path = Path('frontend/src/features/receipts/KassaPage.jsx')
text = path.read_text(encoding='utf-8')

# Herstel de door R9-32F per ongeluk verwijderde nullish-coalescing operators.
patterns = [
    (r'(receipt\?\.total_amount)\s+\'\'', r"\1 ?? ''"),
    (r'(line\?\.display_label)\s+(line\?\.corrected_raw_label)\s+(line\?\.raw_label)\s+\'\'', r"\1 ?? \2 ?? \3 ?? ''"),
    (r'(line\?\.display_quantity)\s+(line\?\.corrected_quantity)\s+(line\?\.quantity)\s+\'\'', r"\1 ?? \2 ?? \3 ?? ''"),
    (r'(line\?\.display_unit)\s+(line\?\.corrected_unit)\s+(line\?\.unit)\s+\'\'', r"\1 ?? \2 ?? \3 ?? ''"),
    (r'(line\?\.display_unit_price)\s+(line\?\.corrected_unit_price)\s+(line\?\.unit_price)\s+\'\'', r"\1 ?? \2 ?? \3 ?? ''"),
    (r'(line\?\.display_line_total)\s+(line\?\.corrected_line_total)\s+(line\?\.line_total)\s+\'\'', r"\1 ?? \2 ?? \3 ?? ''"),
    (r'(lineDrafts\[line\.id\]\?\.is_deleted)\s+(line\?\.is_deleted)', r"\1 ?? \2"),
    (r'(line\?\.line_index)\s+0', r"\1 ?? 0"),
    (r'(lineDrafts\[line\.id\]\?\.quantity)\s+(line\?\.display_quantity)\s+(line\?\.quantity)\s+0', r"\1 ?? \2 ?? \3 ?? 0"),
    (r'(lineDrafts\[line\.id\]\?\.unit_price)\s+(line\?\.display_unit_price)\s+(line\?\.unit_price)\s+0', r"\1 ?? \2 ?? \3 ?? 0"),
    (r'(lineDrafts\[line\.id\]\?\.line_total)\s+(line\?\.display_line_total)\s+(line\?\.line_total)\s+0', r"\1 ?? \2 ?? \3 ?? 0"),
    (r'(line\?\.discount_amount)\s+0', r"\1 ?? 0"),
    (r'(lineDrafts\[line\.id\]\?\.line_total)\s+(line\?\.display_line_total)\s+(line\?\.line_total)(\))', r"\1 ?? \2 ?? \3\4"),
    (r'(receipt\?\.discount_total_effective)\s+(receipt\?\.discount_total)', r"\1 ?? \2"),
    (r'(draft\.quantity)\s+\'\'', r"\1 ?? ''"),
    (r'(draft\.unit_price)\s+\'\'', r"\1 ?? ''"),
    (r'(draft\.line_total)\s+\'\'', r"\1 ?? ''"),
    (r'(line\.discount_amount)\s+\'\'', r"\1 ?? ''"),
    (r'String\(value\s+\'\'\)', "String(value ?? '')"),
    (r'(draft\.article_name)\s+\'\'', r"\1 ?? ''"),
    (r'(draft\.unit)\s+\'\'', r"\1 ?? ''"),
    (r'(draft\.quantity)\s+(line\.display_quantity)\s+(line\.quantity)', r"\1 ?? \2 ?? \3"),
    (r'(draft\.unit_price)\s+(line\.display_unit_price)\s+(line\.unit_price)', r"\1 ?? \2 ?? \3"),
    (r'(draft\.line_total)\s+(line\.display_line_total)\s+(line\.line_total)', r"\1 ?? \2 ?? \3"),
    (r'(item\.line_count)\s+0', r"\1 ?? 0"),
    (r'(item\.total_amount)\s+0', r"\1 ?? 0"),
]
for pattern, repl in patterns:
    text = re.sub(pattern, repl, text)

# Alleen veilige zichtbare mojibake in Nederlandse UI-teksten corrigeren.
text = text.replace('â€¦', '...')
text = text.replace('â€˜', "'").replace('â€™', "'")
text = text.replace('â€œ', '"').replace('â€\x9d', '"')
text = text.replace('â€“', '-').replace('â€”', '-')
text = text.replace('GeÃ¯mporteerd', 'Geimporteerd')
text = text.replace(' Â· ', ' - ')

path.write_text(text, encoding='utf-8')
print('R9-32F1 applied: nullish operators restored and mojibake safely corrected')
'@

$py | python -

git --no-pager diff -- frontend/src/features/receipts/KassaPage.jsx

git add frontend/src/features/receipts/KassaPage.jsx
git commit -m 'R9-32F1 restore nullish operators after mojibake fix'
git push

Write-Host 'R9-32F1 toegepast en gepusht.'
