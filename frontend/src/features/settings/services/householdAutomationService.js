const STORAGE_KEY = 'rezzerv_household_auto_consume_on_repurchase'

export function getHouseholdAutomationSettings() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return { autoConsumeOnRepurchase: false }
    }
    const parsed = JSON.parse(raw)
    return {
      autoConsumeOnRepurchase: Boolean(parsed?.autoConsumeOnRepurchase),
    }
  } catch {
    return { autoConsumeOnRepurchase: false }
  }
}

export function saveHouseholdAutomationSettings(settings = {}) {
  const normalized = {
    autoConsumeOnRepurchase: Boolean(settings.autoConsumeOnRepurchase),
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  window.dispatchEvent(new CustomEvent('rezzerv-household-automation-updated', { detail: normalized }))
  return normalized
}
