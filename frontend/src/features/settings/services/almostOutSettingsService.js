import { API_BASE_URL } from '../../../lib/apiClient'
import { fetchJsonWithAuth, getAuthHeaders } from '../../../lib/authSession'

export const ALMOST_OUT_POLICY_MODES = {
  ADVISORY: 'advisory',
  OVERRIDE: 'override',
  OVERRIDE_FALLBACK_TO_STOCK: 'override_fallback_to_stock',
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
    description: 'Gebruik voorspelde uitputting als hoofdregel wanneer er genoeg historie is.',
  },
  {
    value: ALMOST_OUT_POLICY_MODES.OVERRIDE_FALLBACK_TO_STOCK,
    label: 'Leidend met veilige terugval',
    description: 'Gebruik voorspelde uitputting als hoofdregel en val terug op voorraad als historie ontbreekt.',
  },
]

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
    throw new Error(data?.detail || 'Almost-out instellingen konden niet worden geladen.')
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
    throw new Error(data?.detail || 'Almost-out instellingen konden niet worden opgeslagen.')
  }
  return normalizeSettings(data)
}
