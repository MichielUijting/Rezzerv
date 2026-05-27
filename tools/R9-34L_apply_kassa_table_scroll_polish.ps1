$ErrorActionPreference = 'Stop'

function Read-Utf8File([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Bestand ontbreekt: $Path" }
  return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8File([string]$Path, [string]$Content) {
  [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Replace-OrFail([string]$Content, [string]$Needle, [string]$Replacement, [string]$Label) {
  if (-not $Content.Contains($Needle)) { throw "Verwachte tekst niet gevonden voor: $Label" }
  return $Content.Replace($Needle, $Replacement)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$kassaPath = Join-Path $repoRoot 'frontend\src\features\receipts\KassaPage.jsx'
$baseCssPath = Join-Path $repoRoot 'frontend\src\ui\base.css'

$kassa = Read-Utf8File $kassaPath

$oldDetailCard = @'
<ScreenCard style={{ height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>
      <div data-testid="receipt-detail-page" style={{ display: 'grid', gap: '16px', height: '100%', minHeight: 0, overflow: 'hidden' }}>
'@
$newDetailCard = @'
<ScreenCard style={{ minHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT}px`, overflow: 'visible' }}>
      <div data-testid="receipt-detail-page" style={{ display: 'grid', gap: '16px', minHeight: 0, overflow: 'visible' }}>
'@
$kassa = Replace-OrFail $kassa $oldDetailCard $newDetailCard 'receipt detail card fixed-height clipping'

$oldLinesTable = @'
<Table dataTestId="receipt-lines-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(lineColumnWidths), minWidth: buildTableWidth(lineColumnWidths) }}>
'@
$newLinesTable = @'
<Table wrapperClassName="rz-receipt-lines-table-wrapper" tableClassName="rz-receipt-lines-table" dataTestId="receipt-lines-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(lineColumnWidths), minWidth: buildTableWidth(lineColumnWidths) }}>
'@
$kassa = Replace-OrFail $kassa $oldLinesTable $newLinesTable 'receipt lines table classes'

Write-Utf8File $kassaPath $kassa

$css = Read-Utf8File $baseCssPath
$cssAppend = @'

/* R9-34L Kassa table sticky-header and detail-scroll corrections */
.rz-kassa-inbox-table-wrapper {
  max-height: 318px;
  overflow-y: auto;
  overflow-x: auto;
}

.rz-kassa-inbox-table {
  border-collapse: separate;
  border-spacing: 0;
}

.rz-kassa-inbox-table thead {
  position: sticky;
  top: 0;
  z-index: 30;
}

.rz-kassa-inbox-table thead tr.rz-table-header th,
.rz-kassa-inbox-table thead tr.rz-table-filters th {
  position: sticky;
  z-index: 31;
  background-clip: padding-box;
}

.rz-kassa-inbox-table thead tr.rz-table-header th {
  top: 0;
  background: var(--color-brand-primary);
}

.rz-kassa-inbox-table thead tr.rz-table-filters th {
  top: 30px;
  background: var(--color-brand-light);
  z-index: 30;
}

.rz-receipt-lines-table-wrapper {
  max-height: min(56vh, 520px);
  overflow-y: auto;
  overflow-x: auto;
  padding-bottom: 72px;
  scrollbar-gutter: stable both-edges;
}

.rz-receipt-lines-table {
  border-collapse: separate;
  border-spacing: 0;
}

.rz-receipt-lines-table tfoot td {
  background: #ffffff;
}
'@
if (-not $css.Contains('R9-34L Kassa table sticky-header and detail-scroll corrections')) {
  $css = $css + $cssAppend
}
Write-Utf8File $baseCssPath $css

node --check $kassaPath

Write-Host 'R9-34L applied:'
Write-Host '- Kassa inbox table keeps header row and filter row sticky together'
Write-Host '- receipt detail card no longer clips its contents by fixed height'
Write-Host '- receipt line table has extra vertical scroll room to reach bottom rows/actions'

git --no-pager diff -- frontend/src/features/receipts/KassaPage.jsx frontend/src/ui/base.css

git add frontend/src/features/receipts/KassaPage.jsx frontend/src/ui/base.css tools/R9-34L_apply_kassa_table_scroll_polish.ps1
git commit -m 'R9-34L polish Kassa sticky headers and receipt line scroll'
git push

Write-Host 'R9-34L toegepast en gepusht.'
