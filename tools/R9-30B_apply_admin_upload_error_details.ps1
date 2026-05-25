param(
  [switch]$NoCommit
)

$ErrorActionPreference = 'Stop'

function Fail($message) {
  Write-Error "R9-30B apply failed: $message"
  exit 1
}

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Fail "verwachte branch feature/r9-30a-restore-generic-rembg, maar huidige branch is '$branch'"
}

$kassaPath = 'frontend/src/features/receipts/KassaPage.jsx'
$sharedPath = 'frontend/src/features/stores/storeImportShared.jsx'

if (-not (Test-Path $kassaPath)) { Fail "bestand ontbreekt: $kassaPath" }
if (-not (Test-Path $sharedPath)) { Fail "bestand ontbreekt: $sharedPath" }

$kassa = Get-Content $kassaPath -Raw
$shared = Get-Content $sharedPath -Raw

if ($kassa -match 'createUploadTechnicalError') {
  Write-Host 'R9-30B lijkt al toegepast in KassaPage.jsx; geen dubbele patch.'
} else {
  $helperAnchor = @'


async function fetchReceiptImportBatchStatus(householdId, batchId) {
'@
  $helper = @'


function createUploadTechnicalError(response, responseText, endpoint) {
  const contentType = response?.headers?.get?.('content-type') || ''
  const body = String(responseText || '').trim()
  const isHtml = /^<html[\s>]/i.test(body) || /^<!doctype\s+html/i.test(body)
  const detail = [
    `Endpoint: ${endpoint}`,
    `HTTP-status: ${response?.status || '-'}`,
    `StatusText: ${response?.statusText || '-'}`,
    `Content-Type: ${contentType || '-'}`,
    `Response-type: ${isHtml ? 'HTML in plaats van JSON' : 'niet-JSON of foutresponse'}`,
    '',
    body.slice(0, 4000) || '(lege response-body)',
  ].join('\n')
  return {
    userMessage: 'Upload mislukt. De server gaf een technische fout terug.',
    detail,
  }
}


async function fetchReceiptImportBatchStatus(householdId, batchId) {
'@
  if (-not $kassa.Contains($helperAnchor)) { Fail 'anchor voor createUploadTechnicalError niet gevonden' }
  $kassa = $kassa.Replace($helperAnchor, $helper)

  $oldThrow = @'
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
  }
'@
  $newThrow = @'
  if (!response.ok) {
    const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
    error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/import')
    throw error
  }
'@
  if (-not $kassa.Contains($oldThrow)) { Fail 'uploadReceiptFile throw-block niet gevonden' }
  $kassa = $kassa.Replace($oldThrow, $newThrow)

  $oldState = @'
  const [transientReceiptPreview, setTransientReceiptPreview] = useState(null)
'@
  $newState = @'
  const [transientReceiptPreview, setTransientReceiptPreview] = useState(null)
  const [technicalUploadError, setTechnicalUploadError] = useState(null)
  const [isTechnicalUploadErrorOpen, setIsTechnicalUploadErrorOpen] = useState(false)
'@
  if (-not $kassa.Contains($oldState)) { Fail 'state-anchor transientReceiptPreview niet gevonden' }
  $kassa = $kassa.Replace($oldState, $newState)

  $oldReset = @'
  function resetUploadProgress() {
    setUploadProgress({ active: false, label: '', detail: '', percent: 0 })
  }

  function buildPostImportProgressMessage(kindLabel) {
'@
  $newReset = @'
  function resetUploadProgress() {
    setUploadProgress({ active: false, label: '', detail: '', percent: 0 })
  }

  function clearTechnicalUploadError() {
    setTechnicalUploadError(null)
    setIsTechnicalUploadErrorOpen(false)
  }

  function buildPostImportProgressMessage(kindLabel) {
'@
  if (-not $kassa.Contains($oldReset)) { Fail 'resetUploadProgress-anchor niet gevonden' }
  $kassa = $kassa.Replace($oldReset, $newReset)

  $kassa = $kassa.Replace("    resetUploadProgress()`n    navigate('/kassa/nieuw')", "    resetUploadProgress()`n    clearTechnicalUploadError()`n    navigate('/kassa/nieuw')")
  $kassa = $kassa.Replace("    setReceiptInboxFocusId('')`n    setTimeout(() => fileInputRef.current?.click(), 0)", "    setReceiptInboxFocusId('')`n    clearTechnicalUploadError()`n    setTimeout(() => fileInputRef.current?.click(), 0)")
  $kassa = $kassa.Replace("    setEmailRouteError('')`n    try {`n      const result = await uploadReceiptFile(householdId, file)", "    setEmailRouteError('')`n    clearTechnicalUploadError()`n    try {`n      const result = await uploadReceiptFile(householdId, file)")

  $oldCatch = @'
    } catch (err) {
      setEmailRouteError(normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
      setError('')
      setIsUploading(false)
      resetUploadProgress()
'@
  $newCatch = @'
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)
      setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
      setError('')
      setIsUploading(false)
      resetUploadProgress()
'@
  if (-not $kassa.Contains($oldCatch)) { Fail 'catch-block processReceiptFileImport niet gevonden' }
  $kassa = $kassa.Replace($oldCatch, $newCatch)

  $oldParams = @'
  uploadProgress,
  showHeading = true,
  showSupportPanels = true,
}) {
'@
  $newParams = @'
  uploadProgress,
  technicalUploadError,
  isTechnicalUploadErrorOpen = false,
  onToggleTechnicalUploadError,
  currentUserDisplayRole = 'viewer',
  showHeading = true,
  showSupportPanels = true,
}) {
'@
  if (-not $kassa.Contains($oldParams)) { Fail 'ReceiptSourceHubContent-parameter-anchor niet gevonden' }
  $kassa = $kassa.Replace($oldParams, $newParams)

  $oldErrorRender = @'
            {emailRouteError ? <div className="rz-inline-feedback rz-inline-feedback--error">{emailRouteError}</div> : null}
'@
  $newErrorRender = @'
            {emailRouteError ? <div className="rz-inline-feedback rz-inline-feedback--error">{emailRouteError}</div> : null}
            {emailRouteError && currentUserDisplayRole === 'admin' && technicalUploadError?.detail ? (
              <div style={{ display: 'grid', gap: '8px' }}>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onToggleTechnicalUploadError}
                  data-testid="kassa-admin-technical-error-toggle"
                  style={{ width: 'fit-content' }}
                >
                  {isTechnicalUploadErrorOpen ? 'Verberg technische foutmelding' : 'Toon technische foutmelding'}
                </Button>
                {isTechnicalUploadErrorOpen ? (
                  <pre
                    data-testid="kassa-admin-technical-error-details"
                    style={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '320px',
                      overflow: 'auto',
                      padding: '12px',
                      border: '1px solid #D0D5DD',
                      borderRadius: '8px',
                      background: '#101828',
                      color: '#F9FAFB',
                      fontSize: '12px',
                    }}
                  >
                    {technicalUploadError.detail}
                  </pre>
                ) : null}
              </div>
            ) : null}
'@
  if (-not $kassa.Contains($oldErrorRender)) { Fail 'emailRouteError-render-anchor niet gevonden' }
  $kassa = $kassa.Replace($oldErrorRender, $newErrorRender)

  $oldInvocation = @'
            uploadProgress={uploadProgress}
'@
  $newInvocation = @'
            uploadProgress={uploadProgress}
            technicalUploadError={technicalUploadError}
            isTechnicalUploadErrorOpen={isTechnicalUploadErrorOpen}
            onToggleTechnicalUploadError={() => setIsTechnicalUploadErrorOpen((current) => !current)}
            currentUserDisplayRole={currentUserDisplayRole}
'@
  $count = ([regex]::Matches($kassa, [regex]::Escape($oldInvocation))).Count
  if ($count -lt 2) { Fail "verwacht minimaal 2 ReceiptSourceHubContent uploadProgress-invocations, gevonden: $count" }
  $kassa = $kassa.Replace($oldInvocation, $newInvocation)
}

$oldShared = "return 'De server gaf een onleesbare foutmelding terug.'"
$newShared = "return 'Upload mislukt. De server gaf een technische fout terug.'"
if ($shared.Contains($oldShared)) {
  $shared = $shared.Replace($oldShared, $newShared)
} else {
  Write-Host 'Generieke onleesbare-foutmelding niet gevonden of al aangepast in storeImportShared.jsx.'
}

Set-Content $kassaPath $kassa -Encoding UTF8
Set-Content $sharedPath $shared -Encoding UTF8

Write-Host 'R9-30B patch toegepast. Diff:'
git diff -- $kassaPath $sharedPath

if (-not $NoCommit) {
  git add $kassaPath $sharedPath
  git commit -m 'R9-30B add admin-only upload error details in Kassa'
  git push
  Write-Host 'R9-30B commit gepusht.'
} else {
  Write-Host 'NoCommit gebruikt; commit/push overgeslagen.'
}
