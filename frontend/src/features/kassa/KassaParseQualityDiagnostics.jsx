import { useLayoutEffect, useMemo, useState } from 'react'

const RECEIPT_RESPONSE_EVENT = 'rezzerv:kassa-receipt-response'

function asText(value, fallback = '-') {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function normalizeSpaces(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim()
}

function normalizedArticleName(line) {
  return normalizeSpaces(
    line?.display_label ??
    line?.corrected_raw_label ??
    line?.normalized_label ??
    line?.raw_label ??
    ''
  )
}

function rawLineText(line) {
  return normalizeSpaces(line?.raw_label ?? line?.corrected_raw_label ?? line?.display_label ?? line?.normalized_label ?? '')
}

function cleanLineText(line) {
  return normalizeSpaces(line?.normalized_label ?? line?.display_label ?? line?.corrected_raw_label ?? line?.raw_label ?? '')
}

function amountText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function quantityText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return number.toLocaleString('nl-NL', { minimumFractionDigits: Number.isInteger(number) ? 0 : 2, maximumFractionDigits: 3 })
}

function scoreText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return number.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 3 })
}

function quantityValue(line) {
  return line?.display_quantity ?? line?.corrected_quantity ?? line?.quantity ?? ''
}

function unitValue(line) {
  return line?.display_unit ?? line?.corrected_unit ?? line?.unit ?? ''
}

function packageSizeLabel(line) {
  const quantity = quantityValue(line)
  const unit = asText(unitValue(line), '')
  if (quantity === null || quantity === undefined || quantity === '') return '-'
  return `${quantityText(quantity)}${unit ? ` ${unit}` : ''}`.trim()
}

function offQueryForLine(line) {
  const article = normalizedArticleName(line).toLowerCase()
  const unit = asText(unitValue(line), '').toLowerCase()
  const quantity = quantityValue(line)
  const packagingUnits = new Set(['g', 'gr', 'gram', 'kg', 'ml', 'cl', 'l', 'liter'])
  if (article && quantity !== '' && quantity !== null && quantity !== undefined && packagingUnits.has(unit)) {
    return `${article} ${quantityText(quantity)} ${unit}`.trim()
  }
  return article || '-'
}

function linePrice(line) {
  return line?.display_line_total ?? line?.corrected_line_total ?? line?.line_total ?? ''
}

function parserStatus(line) {
  const raw = rawLineText(line)
  const clean = cleanLineText(line)
  const total = linePrice(line)
  if (raw && clean && total !== '' && total !== null && total !== undefined) return 'diagnose beschikbaar'
  if (raw || clean) return 'controle nodig'
  return 'onbekend'
}

function findReceiptPayload(payload) {
  if (!payload || typeof payload !== 'object') return null
  if (Array.isArray(payload?.lines)) return payload
  if (payload?.receipt && Array.isArray(payload.receipt.lines)) return payload.receipt
  if (payload?.data && Array.isArray(payload.data.lines)) return payload.data
  return null
}

function isReceiptApiUrl(input) {
  const value = typeof input === 'string' ? input : input?.url
  if (!value) return false
  return String(value).includes('/api/receipts/')
}

export function installKassaReceiptDiagnosticsFetchProbe() {
  if (typeof window === 'undefined') return () => {}
  const currentFetch = window.fetch
  if (currentFetch?.__rezzervKassaDiagnosticsProbe) return () => {}

  const probedFetch = async (...args) => {
    const response = await currentFetch(...args)
    try {
      const requestInit = args[1] || {}
      const method = String(requestInit?.method || args[0]?.method || 'GET').toUpperCase()
      if (isReceiptApiUrl(args[0]) && ['GET', 'PATCH', 'POST'].includes(method)) {
        response.clone().json().then((payload) => {
          const receipt = findReceiptPayload(payload)
          if (receipt) {
            window.dispatchEvent(new CustomEvent(RECEIPT_RESPONSE_EVENT, { detail: receipt }))
          }
        }).catch(() => {})
      }
    } catch {
      // Diagnostiek mag de normale Kassa-flow nooit beïnvloeden.
    }
    return response
  }

  probedFetch.__rezzervKassaDiagnosticsProbe = true
  probedFetch.__rezzervOriginalFetch = currentFetch
  window.fetch = probedFetch
  return () => {
    if (window.fetch === probedFetch) window.fetch = currentFetch
  }
}

export default function KassaParseQualityDiagnostics() {
  const [receipt, setReceipt] = useState(null)
  const [expanded, setExpanded] = useState(false)

  useLayoutEffect(() => {
    function handleReceipt(event) {
      setReceipt(event.detail || null)
    }
    window.addEventListener(RECEIPT_RESPONSE_EVENT, handleReceipt)
    return () => window.removeEventListener(RECEIPT_RESPONSE_EVENT, handleReceipt)
  }, [])

  const rows = useMemo(() => {
    const lines = Array.isArray(receipt?.lines) ? receipt.lines : []
    return lines.map((line, index) => ({
      id: asText(line?.id, `line-${index}`),
      index: Number(line?.line_index ?? index) + 1,
      rawLine: rawLineText(line) || '-',
      cleanLine: cleanLineText(line) || '-',
      articleName: normalizedArticleName(line) || '-',
      quantity: quantityText(quantityValue(line)),
      unit: asText(unitValue(line)),
      packageSize: packageSizeLabel(line),
      linePrice: amountText(linePrice(line)),
      offQuery: offQueryForLine(line),
      parserStatus: parserStatus(line),
      parserConfidence: scoreText(line?.confidence_score ?? receipt?.confidence_score),
    }))
  }, [receipt])

  const receiptLabel = receipt?.store_name || receipt?.id || 'geen bon geselecteerd'

  return (
    <div data-testid="kassa-parse-quality-diagnostics" style={{ position: 'fixed', right: 18, bottom: 18, zIndex: 1100, width: expanded ? 'min(1120px, calc(100vw - 36px))' : 'auto', maxHeight: expanded ? '70vh' : 'auto' }}>
      <button type="button" onClick={() => setExpanded((value) => !value)} style={{ border: '1px solid #166534', background: '#166534', color: '#fff', borderRadius: 10, padding: '10px 14px', fontWeight: 700, boxShadow: '0 8px 24px rgba(16, 24, 40, 0.18)' }}>
        Inleeskwaliteit
      </button>
      {expanded ? (
        <div style={{ marginTop: 10, background: '#fff', border: '1px solid #D0D5DD', borderRadius: 14, boxShadow: '0 12px 32px rgba(16, 24, 40, 0.22)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #EAECF0', display: 'grid', gap: 4 }}>
            <strong>Kassa parsekwaliteit diagnose</strong>
            <span style={{ color: '#475467', fontSize: 13 }}>Bon: {receiptLabel}. Alleen diagnose; geen voorraadmutatie, geen koppeling en geen productgroep-toewijzing.</span>
          </div>
          <div style={{ overflow: 'auto', maxHeight: '52vh' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#F2F4F7' }}>
                  {['#', 'Ruwe regel', 'Schone regel', 'Artikelnaam', 'Hoeveelheid', 'Eenheid', 'Verpakking', 'Prijs', 'OFF zoektekst', 'Parserstatus', 'Zekerheid'].map((header) => (
                    <th key={header} style={{ textAlign: header === '#' ? 'right' : 'left', padding: '8px 10px', borderBottom: '1px solid #D0D5DD', whiteSpace: 'nowrap' }}>{header}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.length ? rows.map((row) => (
                  <tr key={row.id}>
                    <td style={{ textAlign: 'right', padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.index}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.rawLine}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.cleanLine}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.articleName}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0', textAlign: 'right' }}>{row.quantity}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.unit}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.packageSize}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0', textAlign: 'right' }}>{row.linePrice}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.offQuery}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0' }}>{row.parserStatus}</td>
                    <td style={{ padding: '8px 10px', borderBottom: '1px solid #EAECF0', textAlign: 'right' }}>{row.parserConfidence}</td>
                  </tr>
                )) : (
                  <tr><td colSpan="11" style={{ padding: '12px 16px', color: '#667085' }}>Selecteer of open een kassabon om de parsekwaliteit per bonregel te zien.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  )
}
