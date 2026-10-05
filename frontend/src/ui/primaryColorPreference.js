export const DEFAULT_PRIMARY_COLOR = '#005F6A'

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
  if (typeof document === 'undefined') return DEFAULT_PRIMARY_COLOR
  return normalizePrimaryColor(document.documentElement.dataset.inhuisPrimaryColor) || DEFAULT_PRIMARY_COLOR
}

export function initializePrimaryColorPreference() {
  const initial = applyPrimaryColorPreference(DEFAULT_PRIMARY_COLOR)
  if (typeof fetch !== 'undefined') {
    fetch('/api/platform/primary-color', {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => {
        const color = normalizePrimaryColor(payload?.primary_color)
        if (color && isReadablePrimaryColor(color)) applyPrimaryColorPreference(color)
      })
      .catch(() => {})
  }
  return initial
}

export function writePrimaryColorPreference(value) {
  const color = normalizePrimaryColor(value)
  if (!color) throw new Error(`Vul een geldige hexkleur in, bijvoorbeeld ${DEFAULT_PRIMARY_COLOR}.`)
  if (!isReadablePrimaryColor(color)) {
    throw new Error('Kies een donkerdere kleur zodat witte tekst goed leesbaar blijft.')
  }
  return applyPrimaryColorPreference(color)
}

export function resetPrimaryColorPreference() {
  return applyPrimaryColorPreference(DEFAULT_PRIMARY_COLOR)
}
