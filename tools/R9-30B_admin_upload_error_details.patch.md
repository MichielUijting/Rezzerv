# R9-30B — Admin-only technische uploadfoutdetails in Kassa

Doel: gewone gebruiker ziet een korte uploadfout; admin krijgt in Kassa een knop om technische foutdetails te openen.

Branch: `feature/r9-30a-restore-generic-rembg`

## Patch-overzicht

### 1. `frontend/src/features/receipts/KassaPage.jsx`

Voeg na `inboxStatusAccentColor(...)` toe:

```jsx
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
```

Wijzig `uploadReceiptFile(...)` bij `if (!response.ok)` van:

```jsx
throw new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
```

naar:

```jsx
const error = new Error(normalizeErrorMessage(data?.detail || data || response.statusText))
error.technicalUploadError = createUploadTechnicalError(response, responseText, '/api/receipts/import')
throw error
```

Voeg state toe bij de andere uploadstates:

```jsx
const [technicalUploadError, setTechnicalUploadError] = useState(null)
const [isTechnicalUploadErrorOpen, setIsTechnicalUploadErrorOpen] = useState(false)
```

Voeg helper toe in `KassaPage()`:

```jsx
function clearTechnicalUploadError() {
  setTechnicalUploadError(null)
  setIsTechnicalUploadErrorOpen(false)
}
```

Roep `clearTechnicalUploadError()` aan op plekken waar een nieuwe upload of actie start, minimaal in:

- `openSourceHub()`
- `handleChooseReceiptFileFromHub()`
- `processReceiptFileImport(...)` vóór de upload

Wijzig de catch in `processReceiptFileImport(...)` van:

```jsx
setEmailRouteError(normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
```

naar:

```jsx
const technical = err?.technicalUploadError || null
if (technical) setTechnicalUploadError(technical)
setEmailRouteError(technical?.userMessage || normalizeErrorMessage(err?.message) || 'Upload van het bonbestand is mislukt.')
```

Geef aan `ReceiptSourceHubContent` deze props mee, zowel op `/kassa/nieuw` als in de inline Kassa-weergave:

```jsx
technicalUploadError={technicalUploadError}
isTechnicalUploadErrorOpen={isTechnicalUploadErrorOpen}
onToggleTechnicalUploadError={() => setIsTechnicalUploadErrorOpen((current) => !current)}
currentUserDisplayRole={currentUserDisplayRole}
```

Breid de functieparameter van `ReceiptSourceHubContent(...)` uit met:

```jsx
technicalUploadError,
isTechnicalUploadErrorOpen = false,
onToggleTechnicalUploadError,
currentUserDisplayRole = 'viewer',
```

Plaats direct onder de bestaande `emailRouteError`-melding:

```jsx
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
```

### 2. `frontend/src/features/stores/storeImportShared.jsx`

Laat `normalizeErrorMessage(...)` voor HTML-responses niet meer de suggestie wekken dat dit normaal/onleesbaar is. Vervang:

```jsx
return 'De server gaf een onleesbare foutmelding terug.'
```

met:

```jsx
return 'Upload mislukt. De server gaf een technische fout terug.'
```

## Acceptatie

- Gewone gebruiker ziet alleen korte melding.
- Admin ziet knop `Toon technische foutmelding`.
- Echte technische foutdetails staan pas onder die knop.
- Geen backend/parser/rembg/statuswijzigingen.
