// Aldi Shop & Go publishes receipts in the app and by email, but no supported
// account API has been established. Use the existing household Kassa file ingest.
const ALLOWED = new Set(['eml', 'pdf', 'png', 'jpg', 'jpeg', 'webp'])
export const ALDI_DIGITAL_MAX_BYTES = 8 * 1024 * 1024

export function validateAldiDigitalFile(file) {
  const name = String(file?.name || '')
  const ext = name.split('.').pop()?.toLowerCase()
  if (!file || !ALLOWED.has(ext)) {
    throw new Error('Kies een Aldi-bon als .eml, .pdf of afbeelding.')
  }
  if (!Number.isSafeInteger(file.size) || file.size < 1 || file.size > ALDI_DIGITAL_MAX_BYTES) {
    throw new Error('De Aldi-bon is leeg of groter dan 8 MB.')
  }
  return { name, extension: ext }
}

export async function importAldiDigitalFile(file, householdId, fetcher = fetch) {
  validateAldiDigitalFile(file)
  if (!householdId || typeof householdId !== 'string') {
    throw new Error('Selecteer eerst een geldig Inhuis-huishouden.')
  }
  const data = new FormData()
  data.append('household_id', householdId)
  data.append('file', file)
  const response = await fetcher('/api/receipts/import', {
    method: 'POST',
    credentials: 'include',
    body: data,
  })
  if (!response?.ok) {
    const detail = await response?.json().catch(() => null)
    throw new Error(String(detail?.detail || 'De Aldi-bon kon niet door Kassa worden ontvangen.'))
  }
  const result = await response.json()
  if (!result || typeof result !== 'object') {
    throw new Error('Inhuis gaf geen herkenbaar importresultaat.')
  }
  return result
}
