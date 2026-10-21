// Deterministic Jumbo batch rules. No account credentials or database operations here.
export const JUMBO_BATCH_LIMIT = 10
export const JUMBO_MAX_PAGES = 30

export function jumboDay(value) {
  if (typeof value !== 'string') return ''
  const m = value.match(/^(20\d{2})-(\d{2})-(\d{2})(?:T.*)?$/)
  if (!m) return ''
  const day = m[1] + '-' + m[2] + '-' + m[3]
  const dt = new Date(day + 'T00:00:00Z')
  return !Number.isNaN(dt.valueOf()) && dt.toISOString().slice(0, 10) === day ? day : ''
}

export function jumboDateWindow(from, to) {
  const start = jumboDay(from)
  const end = jumboDay(to)
  if (!start || !end || start !== from || end !== to || start > end) {
    throw new Error('Stel een geldige Jumbo-begindatum en einddatum in.')
  }
  return { from_date: start, to_date: end }
}

export function selectJumboHistory(receipts, from, to, max = JUMBO_BATCH_LIMIT) {
  jumboDateWindow(from, to)
  if (!Array.isArray(receipts) || receipts.length > 5000 ||
      !Number.isInteger(max) || max < 1 || max > JUMBO_BATCH_LIMIT) {
    throw new Error('Ongeldige Jumbo-geschiedenislijst.')
  }
  const selected = []
  const seen = new Set()
  for (const [index, receipt] of receipts.entries()) {
    const id = typeof receipt?.transactionId === 'string' ? receipt.transactionId.trim() : ''
    const day = jumboDay(receipt?.purchaseEndOn)
    const prefix = 'Jumbo-historie, regel ' + String(index + 1) + ': '
    if (!id) {
      throw new Error(prefix + 'bonnummer ontbreekt of is geen tekst. Geen import uitgevoerd.')
    }
    if (!/^[A-Za-z0-9_-]{4,100}$/.test(id)) {
      const reason = id.length < 4 ? 'te kort' :
        id.length > 100 ? 'te lang' :
        /\\s/.test(id) ? 'bevat spaties of witruimte' :
        /[^\\x00-\\x7F]/.test(id) ? 'bevat niet-ASCII-tekens' :
        'bevat een niet-toegestaan scheidingsteken'
      throw new Error(prefix + 'bonnummer heeft een onverwacht formaat (' + reason + '). Geen import uitgevoerd.')
    }
    if (!day) {
      throw new Error(prefix + 'aankoopdatum ontbreekt of is ongeldig. Geen import uitgevoerd.')
    }
    if (seen.has(id)) throw new Error('Dubbel Jumbo-bonnummer in de geschiedenislijst.')
    seen.add(id)
    if (day >= from && day <= to) selected.push(receipt)
  }
  if (selected.length > max) {
    throw new Error('Meer dan ' + max + ' Jumbo-bonnen in deze periode. Kies een kleinere periode.')
  }
  return selected
}

export function jumboImportResult(result) {
  if (result?.refreshed_existing_receipt) return 'refreshed'
  if (result?.duplicate === true) return 'known'
  if (result?.duplicate === false && result?.raw_receipt_id) return 'new'
  throw new Error('Inhuis gaf geen herkenbare Jumbo-importbevestiging.')
}

export async function importJumboBatch(payload, importOne, buildEnvelope) {
  if (!payload?.ok || !Array.isArray(payload.details) ||
      payload.details.length > JUMBO_BATCH_LIMIT || !payload.details.length) {
    throw new Error('Er zijn geen bevestigde Jumbo-bonnen voor verwerking.')
  }
  const ids = new Set()
  const envelopes = []
  // Validate entire batch first, so syntactically invalid source data never
  // produces a partial write. Runtime/network failures may still partial-write:
  // report each successful receipt and fail closed on the first failed one.
  for (const detail of payload.details) {
    const envelope = buildEnvelope({ ...payload, first_detail: detail })
    if (ids.has(envelope.external_receipt_id)) {
      throw new Error('Dubbel Jumbo-bonnummer binnen deze import.')
    }
    ids.add(envelope.external_receipt_id)
    envelopes.push(envelope)
  }
  const counts = { new: 0, known: 0, refreshed: 0, failed: 0 }
  for (const envelope of envelopes) {
    try {
      const result = await importOne(envelope)
      counts[jumboImportResult(result)] += 1
    } catch (error) {
      counts.failed += 1
      error.jumboCounts = counts
      error.jumboProcessed = counts.new + counts.known + counts.refreshed
      throw error
    }
  }
  return counts
}
