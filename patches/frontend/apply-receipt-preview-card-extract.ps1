$ErrorActionPreference = 'Stop'

$target = 'frontend/src/features/receipts/KassaPage.jsx'
$component = 'frontend/src/features/kassa/components/ReceiptPreviewCard.jsx'

if (-not (Test-Path $target)) {
  throw "Doelbestand ontbreekt: $target"
}
if (-not (Test-Path $component)) {
  throw "Componentbestand ontbreekt: $component. Voer eerst git pull uit."
}

$content = Get-Content $target -Raw

$importLine = "import ReceiptPreviewCard from '../kassa/components/ReceiptPreviewCard.jsx'"
if ($content -match [regex]::Escape($importLine)) {
  Write-Host 'ReceiptPreviewCard import bestaat al. Geen wijziging nodig.'
  exit 0
}

$importAnchor = "import DetailInfoRow from '../kassa/components/DetailInfoRow.jsx'"
$importReplacement = $importAnchor + "`n" + $importLine
if (-not $content.Contains($importAnchor)) {
  throw 'Import-anker DetailInfoRow niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($importAnchor, $importReplacement)

$startMarker = "function ReceiptPreviewCard({ receipt, transientPreview = null, isCollapsed, onToggleCollapse }) {"
$endMarker = "export default function KassaPage"
$startIndex = $content.IndexOf($startMarker)
if ($startIndex -lt 0) {
  throw 'Lokale ReceiptPreviewCard-definitie niet gevonden. Stop om regressie te voorkomen.'
}
$endIndex = $content.IndexOf($endMarker, $startIndex)
if ($endIndex -lt 0) {
  throw 'Eindanker export default function KassaPage niet gevonden. Stop om regressie te voorkomen.'
}

$blockToRemove = $content.Substring($startIndex, $endIndex - $startIndex)
if ($blockToRemove.Length -lt 5000) {
  throw 'Te verwijderen ReceiptPreviewCard-blok is onverwacht klein. Stop om regressie te voorkomen.'
}
if ($blockToRemove -notmatch 'fetchReceiptPreview') {
  throw 'ReceiptPreviewCard-blok bevat verwachte preview-loader niet. Stop om regressie te voorkomen.'
}
if ($blockToRemove -notmatch 'data-testid="receipt-preview-card"') {
  throw 'ReceiptPreviewCard-blok bevat verwachte preview-card test-id niet. Stop om regressie te voorkomen.'
}
if ($blockToRemove -match 'uploadReceiptFile|uploadSharedReceiptFile|uploadEmailReceiptFile|save|approve|parseReceipt') {
  throw 'ReceiptPreviewCard-blok lijkt workflow/businesslogica te bevatten. Stop om regressie te voorkomen.'
}

$content = $content.Remove($startIndex, $endIndex - $startIndex)

$usagePattern = "<ReceiptPreviewCard`n                    receipt={selectedReceipt}`n                    transientPreview={transientPreview}`n                    isCollapsed={isPreviewCollapsed}`n                    onToggleCollapse={() => setIsPreviewCollapsed((value) => !value)}`n                  />"
$usageReplacement = "<ReceiptPreviewCard`n                    receipt={selectedReceipt}`n                    transientPreview={transientPreview}`n                    isCollapsed={isPreviewCollapsed}`n                    onToggleCollapse={() => setIsPreviewCollapsed((value) => !value)}`n                    loadReceiptPreview={fetchReceiptPreview}`n                  />"
if ($content.Contains($usagePattern)) {
  $content = $content.Replace($usagePattern, $usageReplacement)
} elseif ($content -notmatch 'loadReceiptPreview=\{fetchReceiptPreview\}') {
  throw 'ReceiptPreviewCard usage-anker niet gevonden. Stop om regressie te voorkomen.'
}

$backup = "$target.bak-receipt-preview-card"
Copy-Item $target $backup -Force
Set-Content $target $content -NoNewline

Write-Host "ReceiptPreviewCard extractie toegepast. Backup: $backup"
Write-Host 'Controleer nu met: git diff -- frontend/src/features/receipts/KassaPage.jsx'
