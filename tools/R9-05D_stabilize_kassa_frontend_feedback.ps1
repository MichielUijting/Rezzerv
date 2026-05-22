$ErrorActionPreference = 'Stop'

$path = 'frontend\src\features\receipts\KassaPage.jsx'
if (!(Test-Path $path)) {
  throw "KassaPage.jsx niet gevonden op $path"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$path.R9-05D_backup_$timestamp"
Copy-Item $path $backupPath -Force
Write-Host "Backup gemaakt: $backupPath"

$content = Get-Content $path -Raw -Encoding UTF8

# 1. Polling minder agressief maken: refresh alleen bij focus/handmatige reload, niet elke 5 seconden.
$content = $content.Replace(
  'const RECEIPT_INBOX_AUTO_REFRESH_MS = 5000',
  'const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000'
)

# 2. Extra ref tegen overlappende silent refreshes.
if (!$content.Contains('const receiptInboxRefreshInFlightRef = useRef(false)')) {
  $content = $content.Replace(
    '  const uploadBatchLastProcessedRef = useRef(-1)' + "`r`n",
    '  const uploadBatchLastProcessedRef = useRef(-1)' + "`r`n" + '  const receiptInboxRefreshInFlightRef = useRef(false)' + "`r`n"
  )
  Write-Host 'Refresh in-flight guard toegevoegd.'
} else {
  Write-Host 'Refresh in-flight guard bestond al.'
}

# 3. Succesvolle loadReceipts wist stale errors en duplicate notices, ook bij silent refresh.
$content = $content.Replace(
  "      setReceipts([...items])`r`n      pruneReceiptUiState(items)",
  "      setReceipts([...items])`r`n      pruneReceiptUiState(items)`r`n      setError('')`r`n      if (!options?.preserveDuplicateNotice) setDuplicateNotice('')"
)

# 4. Polling-effect vervangen door guarded focus/interval-refresh zonder overlap.
$oldEffect = @'
  useEffect(() => {
    if (isAddReceiptRoute || isUploading) return undefined
    let cancelled = false
    const refreshKassaInbox = () => {
      if (cancelled) return
      loadReceipts(householdId, { silent: true }).catch(() => {})
    }
    refreshKassaInbox()
    const intervalId = window.setInterval(refreshKassaInbox, RECEIPT_INBOX_AUTO_REFRESH_MS)
    window.addEventListener('focus', refreshKassaInbox)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshKassaInbox)
    }
  }, [householdId, isAddReceiptRoute, isUploading])
'@
$newEffect = @'
  useEffect(() => {
    if (isAddReceiptRoute || isUploading) return undefined
    let cancelled = false
    const refreshKassaInbox = async () => {
      if (cancelled || receiptInboxRefreshInFlightRef.current) return
      receiptInboxRefreshInFlightRef.current = true
      try {
        await loadReceipts(householdId, { silent: true })
      } finally {
        receiptInboxRefreshInFlightRef.current = false
      }
    }
    const intervalId = window.setInterval(refreshKassaInbox, RECEIPT_INBOX_AUTO_REFRESH_MS)
    window.addEventListener('focus', refreshKassaInbox)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
      window.removeEventListener('focus', refreshKassaInbox)
      receiptInboxRefreshInFlightRef.current = false
    }
  }, [householdId, isAddReceiptRoute, isUploading])
'@
if ($content.Contains($oldEffect)) {
  $content = $content.Replace($oldEffect, $newEffect)
  Write-Host 'Polling-effect gestabiliseerd.'
} elseif ($content.Contains('receiptInboxRefreshInFlightRef.current')) {
  Write-Host 'Polling-effect leek al gestabiliseerd.'
} else {
  throw 'Polling-effect anchor niet gevonden.'
}

[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
$content = Get-Content $path -Raw -Encoding UTF8

Write-Host 'Controle verplichte wijzigingen:'
$checks = @(
  'const RECEIPT_INBOX_AUTO_REFRESH_MS = 60000',
  'const receiptInboxRefreshInFlightRef = useRef(false)',
  'receiptInboxRefreshInFlightRef.current = true',
  "setError('')",
  "if (!options?.preserveDuplicateNotice) setDuplicateNotice('')"
)
foreach ($check in $checks) {
  if (!$content.Contains($check)) {
    throw "Controle mislukt; ontbreekt: $check"
  }
  Write-Host "OK: $check"
}

Write-Host ''
Write-Host 'Volgende commando''s:'
Write-Host 'npm --prefix frontend run build'
Write-Host 'git add frontend\src\features\receipts\KassaPage.jsx tools\R9-05D_stabilize_kassa_frontend_feedback.ps1'
Write-Host 'git commit -m "R9-05D Stabilize Kassa frontend feedback refresh"'
Write-Host 'git push'
