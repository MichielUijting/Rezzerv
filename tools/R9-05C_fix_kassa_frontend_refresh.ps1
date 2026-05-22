$ErrorActionPreference = 'Stop'

$path = 'frontend\src\features\receipts\KassaPage.jsx'
if (!(Test-Path $path)) {
  throw "KassaPage.jsx niet gevonden op $path"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$path.R9-05C_backup_$timestamp"
Copy-Item $path $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $path -Raw -Encoding UTF8

if (!$content.Contains('const RECEIPT_INBOX_AUTO_REFRESH_MS = 5000')) {
  $content = $content.Replace(
    "const MAX_CAMERA_DIMENSION = 1800`n",
    "const MAX_CAMERA_DIMENSION = 1800`nconst RECEIPT_INBOX_AUTO_REFRESH_MS = 5000`n"
  )
  Write-Host 'Auto-refresh constante toegevoegd.'
} else {
  Write-Host 'Auto-refresh constante bestond al.'
}

$helper = @'

  function pruneReceiptUiState(apiItems = []) {
    const apiItemIds = new Set((apiItems || []).map((item) => String(item?.receipt_table_id || '')).filter(Boolean))
    setDeletedReceiptIds((current) => {
      const next = current.filter((id) => apiItemIds.has(String(id)))
      if (next.length !== current.length) persistStoredReceiptIds(DELETED_RECEIPTS_STORAGE_KEY, next)
      return next
    })
    setSelectedReceiptIds((current) => current.filter((id) => apiItemIds.has(String(id))))
    setReceiptInboxFocusId((current) => (current && !apiItemIds.has(String(current)) ? '' : current))
  }
'@

if (!$content.Contains('function pruneReceiptUiState(apiItems = [])')) {
  $anchor = @'
  async function loadReceipts(nextHouseholdId = householdId, options = {}) {
'@
  if (!$content.Contains($anchor)) {
    throw 'Anchor voor loadReceipts niet gevonden.'
  }
  $content = $content.Replace($anchor, $helper + "`n" + $anchor)
  Write-Host 'Helper toegevoegd: pruneReceiptUiState.'
} else {
  Write-Host 'Helper bestond al: pruneReceiptUiState.'
}

$content = $content.Replace(
  "  async function loadReceipts(nextHouseholdId = householdId, options = {}) {`n    setIsLoading(true)`n    setError('')",
  "  async function loadReceipts(nextHouseholdId = householdId, options = {}) {`n    if (!options?.silent) setIsLoading(true)`n    if (!options?.silent) setError('')"
)

$content = $content.Replace(
  "      items = Array.isArray(list?.items) ? list.items : []`n      setReceipts(items)",
  "      items = Array.isArray(list?.items) ? list.items : []`n      setReceipts([...items])`n      pruneReceiptUiState(items)"
)

$content = $content.Replace(
  "    } finally {`n      setIsLoading(false)`n    }`n    return items`n  }`n`n  useEffect(() => {`n    let cancelled = false",
  "    } finally {`n      if (!options?.silent) setIsLoading(false)`n    }`n    return items`n  }`n`n  useEffect(() => {`n    if (isAddReceiptRoute || isUploading) return undefined`n    let cancelled = false`n    const refreshKassaInbox = () => {`n      if (cancelled) return`n      loadReceipts(householdId, { silent: true }).catch(() => {})`n    }`n    refreshKassaInbox()`n    const intervalId = window.setInterval(refreshKassaInbox, RECEIPT_INBOX_AUTO_REFRESH_MS)`n    window.addEventListener('focus', refreshKassaInbox)`n    return () => {`n      cancelled = true`n      window.clearInterval(intervalId)`n      window.removeEventListener('focus', refreshKassaInbox)`n    }`n  }, [householdId, isAddReceiptRoute, isUploading])`n`n  useEffect(() => {`n    let cancelled = false"
)

[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))

Write-Host 'Controle verplichte wijzigingen:'
$checks = @(
  'const RECEIPT_INBOX_AUTO_REFRESH_MS = 5000',
  'function pruneReceiptUiState(apiItems = [])',
  'setReceipts([...items])',
  'loadReceipts(householdId, { silent: true })',
  "window.addEventListener('focus', refreshKassaInbox)"
)
foreach ($check in $checks) {
  if (!$content.Contains($check)) {
    throw "Controle mislukt; ontbreekt: $check"
  }
  Write-Host "OK: $check"
}

Write-Host ''
Write-Host 'Volgende commando''s:'
Write-Host 'git diff -- frontend\src\features\receipts\KassaPage.jsx'
Write-Host 'npm --prefix frontend run build'
Write-Host 'git add frontend\src\features\receipts\KassaPage.jsx tools\R9-05C_fix_kassa_frontend_refresh.ps1'
Write-Host 'git commit -m "R9-05C Refresh Kassa inbox from API state"'
Write-Host 'git push'
