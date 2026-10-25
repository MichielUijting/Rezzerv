export function displaySource(value) {
  return String(value ?? '').replace(/Open Food Facts/g, 'OFF')
}

export function displayRecognition(value) {
  return String(value ?? '')
    .replace(/\bsuggestie op\b/gi, 'alleen op')
    .replace(/\bsuggestie\b/gi, 'mogelijke match')
    .replace(/^./, (letter) => letter.toUpperCase())
}

const REDUNDANT_JUMBO_NOTICE = 'Producten gevonden bij Jumbo. De koppeling met het bonartikel is alleen op naam; controleer de suggesties.'

export function displayRetailerEvidenceMessage(evidence) {
  if (evidence?.source === 'Jumbo' && evidence?.status === 'name_suggestions') {
    return String(evidence.message ?? '').replace(REDUNDANT_JUMBO_NOTICE, '').trim()
  }
  return evidence?.message ?? ''
}
