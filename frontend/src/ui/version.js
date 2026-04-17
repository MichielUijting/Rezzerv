// Central place for the build/version label shown in the UI.
//
// Preferred flow:
// - VERSION.txt is the source of truth for a release
// - start.bat passes VERSION.txt to the frontend build as VITE_REZZERV_VERSION
// - /version.json exposes the same version in machine-readable form
// - the UI listens for rezzerv-version-ready so late-loaded version.json stays in sync

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
