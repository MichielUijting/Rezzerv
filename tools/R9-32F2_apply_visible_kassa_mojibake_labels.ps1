$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32F2 apply failed: verkeerde branch: $branch"
  exit 1
}

$path = 'frontend/src/features/receipts/KassaPage.jsx'
$text = Get-Content $path -Raw -Encoding UTF8
$original = $text

# Alleen exacte zichtbare UI-labels vervangen. Geen brede tekenvervanging uitvoeren.
$replacements = [ordered]@{
  'Uploadenâ€¦' = 'Uploaden...'
  'Kassa ladenâ€¦' = 'Kassa laden...'
  'Kassa openenâ€¦' = 'Kassa openen...'
  'Kassabon verwerkenâ€¦' = 'Kassabon verwerken...'
  'Zip-batch verwerkenâ€¦' = 'Zip-batch verwerken...'
  'Opslaanâ€¦' = 'Opslaan...'
  'Goedkeurenâ€¦' = 'Goedkeuren...'
  'E-mail verwerkenâ€¦' = 'E-mail verwerken...'
  'E-mail ladenâ€¦' = 'E-mail laden...'
  'GeÃ¯mporteerd op' = 'Geimporteerd op'
  'â€˜Goedkeuren voor Uitpakkenâ€™' = "'Goedkeuren voor Uitpakken'"
}

foreach ($key in $replacements.Keys) {
  $text = $text.Replace($key, $replacements[$key])
}

if ($text -eq $original) {
  Write-Host 'R9-32F2: geen bekende zichtbare mojibake-labels gevonden.'
} else {
  Set-Content $path $text -Encoding UTF8
  Write-Host 'R9-32F2: zichtbare Kassa-mojibake-labels gecorrigeerd.'
}

# Harde veiligheidscontrole: nullish coalescing mag niet kapot zijn.
$badPatterns = @(
  'receipt?.total_amount  ''''',
  'line?.display_label  line?.corrected_raw_label',
  'lineDrafts[line.id]?.quantity  line?.display_quantity',
  'item.line_count  0'
)
foreach ($pattern in $badPatterns) {
  if ((Get-Content $path -Raw -Encoding UTF8).Contains($pattern)) {
    Write-Error "R9-32F2 safety failed: verdachte kapotte JS-operator gevonden: $pattern"
    exit 1
  }
}

git --no-pager diff -- $path

git add $path
git commit -m 'R9-32F2 fix visible Kassa mojibake labels only'
git push

Write-Host 'R9-32F2 toegepast en gepusht.'
