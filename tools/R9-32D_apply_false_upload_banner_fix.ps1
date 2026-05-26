$ErrorActionPreference = 'Stop'

$branch = (git branch --show-current).Trim()
if ($branch -ne 'feature/r9-30a-restore-generic-rembg') {
  Write-Error "R9-32D apply failed: verkeerde branch: $branch"
  exit 1
}

$path = 'frontend/src/features/receipts/KassaPage.jsx'
$text = Get-Content $path -Raw -Encoding UTF8

$old = @'
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)
      setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
      setError('')
      setIsUploading(false)
      resetUploadProgress()
    } finally {
      setUploadMode('manual')
    }
'@

$new = @'
    } catch (err) {
      const technical = err?.technicalUploadError || null
      if (technical) setTechnicalUploadError(technical)

      let refreshedItems = []
      try {
        refreshedItems = await loadReceipts(householdId, { preserveDuplicateNotice: true })
      } catch {
        refreshedItems = []
      }

      const visibleReceiptCount = Array.isArray(refreshedItems) ? refreshedItems.length : 0
      if (visibleReceiptCount > 0) {
        setEmailRouteError('')
        setError('')
        setDuplicateNotice('')
        setStatus(`Kassa is geladen met ${visibleReceiptCount} bon${visibleReceiptCount === 1 ? '' : 'nen'}. Er was wel een technische uploadmelding; details zijn alleen voor de admin beschikbaar.`)
      } else {
        setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
        setError('')
      }
      setIsUploading(false)
      resetUploadProgress()
    } finally {
      setUploadMode('manual')
    }
'@

if ($text -notlike '*Kassa is geladen met ${visibleReceiptCount} bon*') {
  if (-not $text.Contains($old)) {
    Write-Error 'R9-32D anchor niet gevonden in KassaPage.jsx'
    exit 1
  }
  $text = $text.Replace($old, $new)
  Set-Content $path $text -Encoding UTF8
}

git diff -- $path

git add $path
git commit -m 'R9-32D avoid false upload failure banner when receipts loaded'
git push

Write-Host 'R9-32D toegepast en gepusht.'
