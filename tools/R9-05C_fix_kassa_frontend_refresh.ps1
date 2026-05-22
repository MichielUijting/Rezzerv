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

# Normaliseer eventuele half-uitgevoerde eerdere patchpogingen, zodat het script idempotent blijft.
$content = $content -replace "\r?\nconst RECEIPT_INBOX_AUTO_REFRESH_MS = 5000\r?\n", "`r`n"
$content = $content -replace "\r?\n\s*function pruneReceiptUiState\(apiItems = \[\]\) \{[\s\S]*?\n\s*\}\r?\n\r?\n\s*async function loadReceipts", "`r`n`r`n  async function loadReceipts"
$content = $content -replace "async function loadReceipts\(nextHouseholdId = householdId, options = \{\}\) \{\r?\n\s*if \(!options\?\.silent\) setIsLoading\(true\)\r?\n\s*if \(!options\?\.silent\) setError\(''\)", "async function loadReceipts(nextHouseholdId = householdId, options = {}) {`r`n    setIsLoading(true)`r`n    setError('')"
$content = $content -replace "items = Array\.isArray\(list\?\.items\) \? list\.items : \[\]\r?\n\s*setReceipts\(\[\.\.\.items\]\)\r?\n\s*pruneReceiptUiState\(items\)", "items = Array.isArray(list?.items) ? list.items : []`r`n      setReceipts(items)"
$content = $content -replace "\r?\n\s*useEffect\(\(\) => \{\r?\n\s*if \(isAddReceiptRoute \|\| isUploading\) return undefined[\s\S]*?\r?\n\s*\}, \[householdId, isAddReceiptRoute, isUploading\]\)\r?\n\r?\n\s*useEffect\(\(\) => \{\r?\n\s*let cancelled = false", "`r`n`r`n  useEffect(() => {`r`n    let cancelled = false"

if (!$content.Contains('const RECEIPT_INBOX_AUTO_REFRESH_MS = 5000')) {
  $content = [regex]::Replace(
    $content,
    "const MAX_CAMERA_DIMENSION = 1800",
    "const MAX_CAMERA_DIMENSION = 1800`r`nconst RECEIPT_INBOX_AUTO_REFRESH_MS = 5000",
    1
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
  $anchor = "  async function loadReceipts(nextHouseholdId = householdId, options = {}) {"
  if (!$content.Contains($anchor)) {
    throw 'Anchor voor loadReceipts niet gevonden.'
  }
  $content = $content.Replace($anchor, $helper + "`r`n" + $anchor)
  Write-Host 'Helper toegevoegd: pruneReceiptUiState.'
} else {
  Write-Host 'Helper bestond al: pruneReceiptUiState.'
}

$content = $content.Replace(
  "  async function loadReceipts(nextHouseholdId = householdId, options = {}) {`r`n    setIsLoading(true)`r`n    setError('')",
  "  async function loadReceipts(nextHouseholdId = householdId, options = {}) {`r`n    if (!options?.silent) setIsLoading(true)`r`n    if (!options?.silent) setError('')"
)

$content = $content.Replace(
  "      items = Array.isArray(list?.items) ? list.items : []`r`n      setReceipts(items)",
  "      items = Array.isArray(list?.items) ? list.items : []`r`n      setReceipts([...items])`r`n      pruneReceiptUiState(items)"
)

$content = $content.Replace(
  "    } finally {`r`n      setIsLoading(false)`r`n    }`r`n    return items`r`n  }`r`n`r`n  useEffect(() => {`r`n    let cancelled = false",
  "    } finally {`r`n      if (!options?.silent) setIsLoading(false)`r`n    }`r`n    return items`r`n  }`r`n`r`n  useEffect(() => {`r`n    if (isAddReceiptRoute || isUploading) return undefined`r`n    let cancelled = false`r`n    const refreshKassaInbox = () => {`r`n      if (cancelled) return`r`n      loadReceipts(householdId, { silent: true }).catch(() => {})`r`n    }`r`n    refreshKassaInbox()`r`n    const intervalId = window.setInterval(refreshKassaInbox, RECEIPT_INBOX_AUTO_REFRESH_MS)`r`n    window.addEventListener('focus', refreshKassaInbox)`r`n    return () => {`r`n      cancelled = true`r`n      window.clearInterval(intervalId)`r`n      window.removeEventListener('focus', refreshKassaInbox)`r`n    }`r`n  }, [householdId, isAddReceiptRoute, isUploading])`r`n`r`n  useEffect(() => {`r`n    let cancelled = false"
)

[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
$content = Get-Content $path -Raw -Encoding UTF8

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
