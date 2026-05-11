$ErrorActionPreference = 'Stop'

$target = 'frontend/src/features/receipts/KassaPage.jsx'
$component = 'frontend/src/features/kassa/components/ReceiptStatusBadge.jsx'

if (-not (Test-Path $target)) {
  throw "Doelbestand ontbreekt: $target"
}
if (-not (Test-Path $component)) {
  throw "Componentbestand ontbreekt: $component. Voer eerst git pull uit."
}

$content = Get-Content $target -Raw

if ($content -match "import ReceiptStatusBadge from '../kassa/components/ReceiptStatusBadge.jsx'") {
  Write-Host 'ReceiptStatusBadge import bestaat al. Geen wijziging nodig.'
  exit 0
}

$importAnchor = "import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'"
$importReplacement = $importAnchor + "`nimport ReceiptStatusBadge from '../kassa/components/ReceiptStatusBadge.jsx'"
if (-not $content.Contains($importAnchor)) {
  throw 'Import-anker niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($importAnchor, $importReplacement)

$stylePattern = @'
function inboxStatusStyle(value) {
  if (value === 'Gecontroleerd') {
    return {
      background: '#ECFDF3',
      color: '#027A48',
      border: '1px solid #ABEFC6',
    }
  }
  if (value === 'Controle nodig') {
    return {
      background: '#FFFAEB',
      color: '#166534',
      border: '1px solid #FEDF89',
    }
  }
  return {
    background: '#FFF7ED',
    color: '#166534',
    border: '1px solid #F9DBAF',
  }
}

'@
if (-not $content.Contains($stylePattern)) {
  throw 'Lokale inboxStatusStyle-definitie niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($stylePattern, '')

$badgePattern = @'
function ReceiptStatusBadge({ value }) {
  return (
    <span
      data-testid={`receipt-inbox-status-${String(value || '').toLowerCase().replace(/\s+/g, '-')}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '13px',
        fontWeight: 700,
        whiteSpace: 'nowrap',
        ...inboxStatusStyle(value),
      }}
    >
      {value || '-'}
    </span>
  )
}

'@
if (-not $content.Contains($badgePattern)) {
  throw 'Lokale ReceiptStatusBadge-definitie niet gevonden. Stop om regressie te voorkomen.'
}
$content = $content.Replace($badgePattern, '')

$backup = "$target.bak-receipt-status-badge"
Copy-Item $target $backup -Force
Set-Content $target $content -NoNewline

Write-Host "ReceiptStatusBadge extractie toegepast. Backup: $backup"
Write-Host 'Controleer nu met: git diff -- frontend/src/features/receipts/KassaPage.jsx'
