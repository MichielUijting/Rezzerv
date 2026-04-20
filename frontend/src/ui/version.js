// Central place for the build/version label shown in the UI.

function normalizeVersion(value) {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : ""
}

export function getInjectedRezzervVersionTag() {
  return normalizeVersion(import.meta.env?.VITE_REZZERV_VERSION)
}

export function getWindowRezzervVersionTag() {
  if (typeof window === "undefined") return ""
  return normalizeVersion(window.__REZZERV_VERSION__?.version)
}

export function getRezzervVersionTag() {
  const fromWindow = getWindowRezzervVersionTag()
  if (fromWindow) return fromWindow

  const injected = getInjectedRezzervVersionTag()
  if (injected) return injected

  return "dev"
}

export function formatRezzervVersionLabel(tag) {
  const normalized = normalizeVersion(tag)
  if (!normalized) return "Rezzerv dev"

  // Avoid double prefix like "Rezzerv vRezzerv-MVP..."
  if (normalized.toLowerCase().startsWith("rezzerv")) {
    return normalized
  }

  return `Rezzerv v${normalized}`
}
