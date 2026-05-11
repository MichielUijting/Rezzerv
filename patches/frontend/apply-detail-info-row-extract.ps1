$ErrorActionPreference = 'Stop'

$target = 'frontend/src/features/receipts/KassaPage.jsx'
$component = 'frontend/src/features/kassa/components/DetailInfoRow.jsx'

if (-not (Test-Path $target)) {
  throw "Doelbestand ontbreekt: $target"
}
if (-not (Test-Path $component)) {
  throw "Componentbestand ontbreekt: $component. Voer eerst git pull uit."
}

$content = Get-Content $target -Raw

if ($content -match "import DetailInfoRow from '../kassa/components/DetailInfoRow.jsx'") {
  Write-Host 'DetailInfoRow import bestaat al. Geen wijziging nodig.'
  exit 0
}

$importAnchor = "import ReceiptStatusBadge from '../kassa/components/ReceiptStatusBadge.jsx'"
$importReplacement = $importAnchor + "`nimport DetailInfoRow from '../kassa/components/DetailInfoRow.jsx'"
if (-not $content.Contains($importAnchor)) {
  throw 'Import-anker ReceiptStatusBadge niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($importAnchor, $importReplacement)

$detailInfoRowPattern = @'
function DetailInfoRow({ label, value }) {
  return (
    <div style={{ display: 'grid', gap: '4px' }}>
      <div style={{ fontSize: '13px', fontWeight: 700, color: '#667085' }}>{label}</div>
      <div style={{ fontSize: '15px' }}>{value || '-'}</div>
    </div>
  )
}

'@
if (-not $content.Contains($detailInfoRowPattern)) {
  throw 'Lokale DetailInfoRow-definitie niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($detailInfoRowPattern, '')

$backup = "$target.bak-detail-info-row"
Copy-Item $target $backup -Force
Set-Content $target $content -NoNewline

Write-Host "DetailInfoRow extractie toegepast. Backup: $backup"
Write-Host 'Controleer nu met: git diff -- frontend/src/features/receipts/KassaPage.jsx'
