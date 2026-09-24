export const DEFAULT_PRIMARY_COLOR = '#005F6A'
export const PRIMARY_COLOR_STORAGE_KEY = 'inhuis.ui.primary-color'

const PRIMARY_COLOR_TOKENS = [
  '--color-brand-primary',
  '--color-ui-primary',
  '--color-mobile-ui-primary',
]

export function normalizePrimaryColor(value) {
  const match = String(value || '').trim().match(/^#?([0-9a-f]{6})$/i)
  return match ? `#${match[1].toUpperCase()}` : null
}

function channelToLinear(channel) {
  const value = channel / 255
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

export function contrastWithWhite(value) {
  const color = normalizePrimaryColor(value)
  if (!color) return 0
  const red = channelToLinear(Number.parseInt(color.slice(1, 3), 16))
  const green = channelToLinear(Number.parseInt(color.slice(3, 5), 16))
  const blue = channelToLinear(Number.parseInt(color.slice(5, 7), 16))
  const luminance = (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
  return 1.05 / (luminance + 0.05)
}

export function isReadablePrimaryColor(value) {
  return contrastWithWhite(value) >= 4.5
}

export function applyPrimaryColorPreference(value) {
  const color = normalizePrimaryColor(value) || DEFAULT_PRIMARY_COLOR
  if (typeof document !== 'undefined') {
    for (const token of PRIMARY_COLOR_TOKENS) {
      document.documentElement.style.setProperty(token, color)
    }
    document.documentElement.dataset.inhuisPrimaryColor = color
  }
  return color
}

export function readPrimaryColorPreference() {
  if (typeof window === 'undefined') return DEFAULT_PRIMARY_COLOR
  try {
    const stored = normalizePrimaryColor(window.localStorage.getItem(PRIMARY_COLOR_STORAGE_KEY))
    return stored && isReadablePrimaryColor(stored) ? stored : DEFAULT_PRIMARY_COLOR
  } catch {
    return DEFAULT_PRIMARY_COLOR
  }
}

export function initializePrimaryColorPreference() {
  return applyPrimaryColorPreference(readPrimaryColorPreference())
}

export function writePrimaryColorPreference(value) {
  const color = normalizePrimaryColor(value)
  if (!color) throw new Error(`Vul een geldige hexkleur in, bijvoorbeeld ${DEFAULT_PRIMARY_COLOR}.`)
  if (!isReadablePrimaryColor(color)) {
    throw new Error('Kies een donkerdere kleur zodat witte tekst goed leesbaar blijft.')
  }
  try {
    window.localStorage.setItem(PRIMARY_COLOR_STORAGE_KEY, color)
  } catch {
    throw new Error('De kleurvoorkeur kon niet op dit apparaat worden opgeslagen.')
  }
  return applyPrimaryColorPreference(color)
}

export function resetPrimaryColorPreference() {
  try {
    window.localStorage.removeItem(PRIMARY_COLOR_STORAGE_KEY)
  } catch {
    // De standaardkleur kan ook zonder opslag direct worden toegepast.
  }
  return applyPrimaryColorPreference(DEFAULT_PRIMARY_COLOR)
}
