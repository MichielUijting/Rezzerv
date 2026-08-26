import { useEffect, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import { readStoredAuthContext } from '../../lib/authSession.js'
import {
  fetchHouseholdOnboarding,
  readHouseholdOnboarding,
} from '../onboarding/onboardingState.js'
import SettingsGlobalLocationsPage from './SettingsGlobalLocationsPage.jsx'
import SettingsLocationsPage from './SettingsLocationsPage.jsx'

export default function SettingsLocationsRoutePage() {
  const context = readStoredAuthContext()
  const initialOnboarding = readHouseholdOnboarding(context)
  const [onboarding, setOnboarding] = useState(initialOnboarding)
  const [isLoadingProduct, setIsLoadingProduct] = useState(
    context?.context_type === 'regular' && !initialOnboarding,
  )

  useEffect(() => {
    let cancelled = false

    async function refresh() {
      if (context?.context_type !== 'regular') {
        setIsLoadingProduct(false)
        return
      }
      try {
        const next = await fetchHouseholdOnboarding(context, { force: true })
        if (!cancelled) setOnboarding(next)
      } catch {
        // Keep the legacy page as fail-safe when product relevance cannot be read.
      } finally {
        if (!cancelled) setIsLoadingProduct(false)
      }
    }

    refresh()
    return () => {
      cancelled = true
    }
  }, [context?.user_id, context?.active_household_id, context?.context_type])

  if (isLoadingProduct) {
    return (
      <AppShell title="Locaties" showExit={false}>
        <Card><div data-testid="settings-locations-loading">Locatie-instellingen laden…</div></Card>
      </AppShell>
    )
  }

  const configuration = onboarding?.product_configuration
  if (!configuration || typeof configuration !== 'object') {
    return <SettingsLocationsPage />
  }

  const level = String(configuration.location_tracking_level || '').trim().toLowerCase()
  if (level === 'global') return <SettingsGlobalLocationsPage />
  if (level === 'exact') return <SettingsLocationsPage />

  return (
    <AppShell title="Locaties" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: 14 }} data-testid="settings-locations-inactive">
          <h2 style={{ margin: 0, fontSize: 20 }}>Locatiebeheer is niet actief</h2>
          <p style={{ margin: 0, color: '#667085' }}>
            Dit huishouden gebruikt momenteel geen locaties. Activeer later een locatiemogelijkheid via de productinrichting van Inhuis.
          </p>
        </div>
      </Card>
    </AppShell>
  )
}
