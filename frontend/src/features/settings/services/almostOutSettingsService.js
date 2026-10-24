import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth, getAuthHeaders } from '../../../lib/authSession'

export const ALMOST_OUT_POLICY_MODES = {
  ADVISORY: 'advisory',
  OVERRIDE: 'override',
}

export const ALMOST_OUT_POLICY_OPTIONS = [
  {
    value: ALMOST_OUT_POLICY_MODES.ADVISORY,
    label: 'Aanvullend',
    description: 'Voeg voorspelde uitputting toe als extra almost-out signaal naast de artikelinstelling.',
  },
  {
    value: ALMOST_OUT_POLICY_MODES.OVERRIDE,
    label: 'Leidend',
    description: 'Gebruik de voorspelling wanneer er genoeg aankoopgeschiedenis is. Anders gebruikt Inhuis de minimumvoorraad.',
  },

]

function settingsErrorMessage(detail, fallback) {
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  // FastAPI validation details are arrays of objects, not displayable strings.
  // Keep technical field paths, input values and objects out of user feedback.
  if (Array.isArray(detail)) {
    return 'De instellingen zijn niet opgeslagen. Controleer de gekozen instelling en het aantal dagen.'
  }
  return fallback
}

function normalizeSettings(value = {}) {
  const normalizedPolicyMode = String(value.policy_mode || value.policyMode || ALMOST_OUT_POLICY_MODES.ADVISORY).trim().toLowerCase()
  const allowed = new Set(Object.values(ALMOST_OUT_POLICY_MODES))
  return {
    predictionEnabled: Boolean(value.prediction_enabled ?? value.predictionEnabled),
    predictionDays: Math.max(0, Number(value.prediction_days ?? value.predictionDays ?? 0) || 0),
    policyMode: allowed.has(normalizedPolicyMode) ? normalizedPolicyMode : ALMOST_OUT_POLICY_MODES.ADVISORY,
    isHouseholdAdmin: Boolean(value.is_household_admin ?? value.isHouseholdAdmin),
  }
}

export async function fetchAlmostOutSettings() {
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/almost-out-settings`, {
    method: 'GET',
    headers: { Accept: 'application/json', ...getAuthHeaders() },
    credentials: 'include',
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(settingsErrorMessage(data?.detail, 'De instellingen voor Bijna op konden niet worden geladen.'))
  }
  return normalizeSettings(data)
}

export async function saveAlmostOutSettings(settings = {}) {
  const normalized = normalizeSettings(settings)
  const response = await fetchJsonWithAuth(`${API_BASE_URL}/api/household/almost-out-settings`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...getAuthHeaders(),
    },
    credentials: 'include',
    body: JSON.stringify({
      prediction_enabled: normalized.predictionEnabled,
      prediction_days: normalized.predictionDays,
      policy_mode: normalized.policyMode,
    }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(settingsErrorMessage(data?.detail, 'De instellingen voor Bijna op konden niet worden opgeslagen. Probeer het opnieuw.'))
  }
  return normalizeSettings(data)
}
