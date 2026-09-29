const STORAGE_KEY = 'inhuis-accessibility-font-scale'
export const DEFAULT_FONT_SCALE = 'standard'

export const FONT_SCALE_OPTIONS = Object.freeze({
  standard: { label: 'Standaard', body: '14px', title: '16px' },
  large: { label: 'Groot', body: '17px', title: '20px' },
  extraLarge: { label: 'Extra groot', body: '20px', title: '24px' },
})

export function normalizeFontScale(value) {
  return Object.prototype.hasOwnProperty.call(FONT_SCALE_OPTIONS, value) ? value : DEFAULT_FONT_SCALE
}

export function applyFontScalePreference(value) {
  const normalized = normalizeFontScale(value)
  const option = FONT_SCALE_OPTIONS[normalized]
  const root = document.documentElement
  root.style.setProperty('--font-size-ui-body', option.body)
  root.style.setProperty('--font-size-ui-title', option.title)
  root.dataset.fontScale = normalized
  return normalized
}

export function readFontScalePreference() {
  try {
    return normalizeFontScale(window.localStorage.getItem(STORAGE_KEY))
  } catch {
    return DEFAULT_FONT_SCALE
  }
}

export function writeFontScalePreference(value) {
  const normalized = normalizeFontScale(value)
  window.localStorage.setItem(STORAGE_KEY, normalized)
  return applyFontScalePreference(normalized)
}

export function resetFontScalePreference() {
  try { window.localStorage.removeItem(STORAGE_KEY) } catch {}
  return applyFontScalePreference(DEFAULT_FONT_SCALE)
}

export function initializeFontScalePreference() {
  return applyFontScalePreference(readFontScalePreference())
}
