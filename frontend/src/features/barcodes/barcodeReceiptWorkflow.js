export function normalizeBarcodeInput(value) {
  return String(value || '')
    .replace(/[\s-]+/g, '')
    .trim()
}

export function createIdleBarcodeState() {
  return {
    status: 'idle',
    message: '',
    gtin: '',
    matchStatus: '',
    productName: '',
    globalProductId: '',
    product: null,
  }
}

function firstText(...values) {
  for (const value of values) {
    const normalized = String(value || '').trim()
    if (normalized) return normalized
  }
  return ''
}

export async function validateAndLookupBarcode({
  value,
  requestJson,
  fallbackProductName = '',
}) {
  const normalizedInput = normalizeBarcodeInput(value)
  if (!normalizedInput) {
    return {
      ok: false,
      state: {
        ...createIdleBarcodeState(),
        status: 'warning',
        message: 'Vul eerst een GTIN in.',
      },
    }
  }

  const validation = await requestJson('/api/barcodes/validate', {
    method: 'POST',
    body: JSON.stringify({ value: normalizedInput, declared_type: 'gtin' }),
  })

  if (!validation?.valid) {
    return {
      ok: false,
      state: {
        ...createIdleBarcodeState(),
        status: 'error',
        message: validation?.message
          || validation?.reason
          || 'Dit is geen geldige GTIN-8, 12, 13 of 14.',
      },
    }
  }

  const normalizedGtin = String(
    validation?.normalized_value || normalizedInput
  ).trim()
  const lookup = await requestJson(
    `/api/barcodes/${encodeURIComponent(normalizedGtin)}`,
    { method: 'GET' }
  )
  const matchStatus = String(lookup?.match_status || '').trim()

  if (matchStatus === 'conflict') {
    return {
      ok: false,
      state: {
        ...createIdleBarcodeState(),
        status: 'error',
        message: 'Conflict: deze GTIN verwijst naar meerdere universele artikelen. Er is niets gewijzigd.',
        gtin: normalizedGtin,
        matchStatus,
      },
    }
  }

  const product = lookup?.product || null
  const productName = firstText(
    product?.name,
    fallbackProductName,
    matchStatus === 'matched'
      ? 'bekend universeel artikel'
      : 'Nieuw catalogusproduct'
  )
  const globalProductId = String(
    product?.global_product_id || product?.id || ''
  ).trim()

  return {
    ok: true,
    confirmation: {
      gtin: String(lookup?.gtin || normalizedGtin).trim(),
      matchStatus,
      productName,
      globalProductId,
      product,
    },
    state: {
      status: 'success',
      message: matchStatus === 'matched'
        ? `Geldige GTIN. Gevonden: ${productName}.`
        : 'Dit is een geldige barcode.',
      gtin: String(lookup?.gtin || normalizedGtin).trim(),
      matchStatus,
      productName,
      globalProductId,
      product,
    },
  }
}
