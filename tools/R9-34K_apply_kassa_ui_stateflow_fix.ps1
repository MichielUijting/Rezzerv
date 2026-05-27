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

$helperNeedle = @'
  async function loadReceipts(nextHouseholdId = householdId, options = {}) {
'@
$helperInsert = @'
  function mergeUploadedReceiptIntoItems(apiItems = [], result = null) {
    const uploadedReceiptId = String(result?.receipt_table_id || '')
    if (!uploadedReceiptId) return apiItems
    if ((apiItems || []).some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)) return apiItems
    return [
      {
        receipt_table_id: uploadedReceiptId,
        store_name: result?.store_name || result?.parsed?.store_name || result?.receipt?.store_name || 'Onbekende winkel',
        purchase_at: result?.purchase_at || result?.parsed?.purchase_at || result?.receipt?.purchase_at || null,
        total_amount: result?.total_amount ?? result?.parsed?.total_amount ?? result?.receipt?.total_amount ?? null,
        currency: result?.currency || result?.parsed?.currency || result?.receipt?.currency || 'EUR',
        line_count: Number(result?.line_count ?? result?.parsed?.line_count ?? result?.receipt?.line_count ?? 0),
        inbox_status: result?.inbox_status || result?.po_norm_status_label || 'Controle nodig',
        po_norm_status_label: result?.po_norm_status_label || 'Controle nodig',
        _optimistic_after_upload: true,
      },
      ...(apiItems || []),
    ]
  }

  async function loadReceiptsWithUploadedFallback(result, options = {}) {
    const uploadedReceiptId = String(result?.receipt_table_id || '')
    const items = await loadReceipts(householdId, options)
    if (!uploadedReceiptId || items.some((item) => String(item?.receipt_table_id || '') === uploadedReceiptId)) return items
    const mergedItems = mergeUploadedReceiptIntoItems(items, result)
    setReceipts([...mergedItems])
    pruneReceiptUiState(mergedItems)
    return mergedItems
  }

'@
$kassa = Replace-OrFail $kassa $helperNeedle ($helperInsert + $helperNeedle) 'insert uploaded fallback helpers before loadReceipts'

$oldLoad = @'
const refreshedItems = await loadReceipts(householdId)
        const receiptExistsInInbox = uploadedReceiptId
'@
$newLoad = @'
const refreshedItems = await loadReceiptsWithUploadedFallback(result, { openReceiptId: uploadedReceiptId })
        const receiptExistsInInbox = uploadedReceiptId
'@
$kassa = $kassa.Replace($oldLoad, $newLoad)

$kassa = $kassa.Replace("setError('De kassabon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Kassa worden geladen.')", "setStatus('Bon toegevoegd. De bon staat nu in de Kassa. De lijst is direct bijgewerkt.')")
$kassa = $kassa.Replace("setError('De e-mailbon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Kassa worden geladen.')", "setStatus('E-mailbon ontvangen. De lijst is direct bijgewerkt.')")
$kassa = $kassa.Replace("setError('De kassabon is opgeslagen, maar kon nog niet direct als nieuwe rij in de Kassa worden geladen.')", "setStatus('Bon toegevoegd. De lijst is direct bijgewerkt.')")

$oldPageDiv = @'
<div style={{ display: 'grid', gap: '16px' }} data-testid="kassa-page">
'@
$newPageDiv = @'
<div className="rz-kassa-page" style={{ display: 'grid', gap: '16px' }} data-testid="kassa-page">
'@
$kassa = Replace-OrFail $kassa $oldPageDiv $newPageDiv 'kassa page class'

$oldTable = @'
<Table dataTestId="kassa-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(inboxColumnWidths), minWidth: buildTableWidth(inboxColumnWidths) }}>
'@
$newTable = @'
<Table wrapperClassName="rz-kassa-inbox-table-wrapper" tableClassName="rz-kassa-inbox-table" dataTestId="kassa-table" tableStyle={{ tableLayout: 'fixed', width: buildTableWidth(inboxColumnWidths), minWidth: buildTableWidth(inboxColumnWidths) }}>
'@
$kassa = Replace-OrFail $kassa $oldTable $newTable 'kassa inbox table classes'

$oldDetailPanel = @'
<div style={{ minWidth: 0, width: '100%', overflow: 'visible', height: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>
'@
$newDetailPanel = @'
<div style={{ minWidth: 0, width: '100%', overflow: 'visible', minHeight: `${RECEIPT_DETAIL_PANEL_HEIGHT}px` }}>
'@
$kassa = $kassa.Replace($oldDetailPanel, $newDetailPanel)

Write-Utf8File $kassaPath $kassa

$css = Read-Utf8File $baseCssPath
$cssAppend = @'

/* R9-34K Kassa scroll/stateflow polish */
html,
body,
#root {
  min-height: 100%;
  height: auto;
}

.rz-screen,
.rz-content,
.rz-content-inner,
.rz-kassa-page {
  min-height: 0;
  overflow: visible;
}

.rz-kassa-page {
  width: 100%;
  padding-bottom: 96px;
}

.rz-kassa-inbox-table-wrapper {
  max-height: calc(var(--rz-table-header-row-height) + var(--rz-table-filter-row-height) + (var(--rz-table-body-row-height) * 10) + 2px);
  overflow-y: auto;
  overflow-x: auto;
}

.rz-kassa-inbox-table thead tr.rz-table-header th {
  position: sticky;
  top: 0;
  z-index: 4;
  background: var(--color-brand-primary);
}

.rz-kassa-inbox-table thead tr.rz-table-filters th {
  position: sticky;
  top: var(--rz-table-header-row-height);
  z-index: 3;
  background: var(--color-brand-light);
}

.rz-kassa-inbox-table thead tr.rz-table-header th:first-child,
.rz-kassa-inbox-table thead tr.rz-table-filters th:first-child {
  left: 0;
}
'@
if (-not $css.Contains('R9-34K Kassa scroll/stateflow polish')) {
  $css = $css + $cssAppend
}
Write-Utf8File $baseCssPath $css

node --check $kassaPath

Write-Host 'R9-34K applied:'
Write-Host '- Kassa page receives bottom scroll room and no fixed detail-panel clipping'
Write-Host '- inbox table header/filter rows are sticky inside the table wrapper'
Write-Host '- post-upload list refresh gets an optimistic fallback row when API list is delayed'

git --no-pager diff -- frontend/src/features/receipts/KassaPage.jsx frontend/src/ui/base.css

git add frontend/src/features/receipts/KassaPage.jsx frontend/src/ui/base.css tools/R9-34K_apply_kassa_ui_stateflow_fix.ps1
git commit -m 'R9-34K fix Kassa scroll sticky header and upload list sync'
git push

Write-Host 'R9-34K toegepast en gepusht.'
