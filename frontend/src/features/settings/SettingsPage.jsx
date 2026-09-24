import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import AuthorizedControl from '../../ui/AuthorizedControl'
import Button from '../../ui/Button'
import { readStoredAuthContext } from '../../lib/authSession.js'
import {
  fetchHouseholdOnboarding,
  readHouseholdOnboarding,
} from '../onboarding/onboardingState.js'
import { buildSettingsNavigation } from './settingsNavigation.js'
import {
  DEFAULT_PRIMARY_COLOR,
  normalizePrimaryColor,
  readPrimaryColorPreference,
  resetPrimaryColorPreference,
  writePrimaryColorPreference,
} from '../../ui/primaryColorPreference.js'

const PRIMARY_USE_CASE_LABELS = {
  inhuis_halen: 'Inhuis halen',
  wat_inhuis: 'Wat Inhuis',
  waar_inhuis: 'Waar Inhuis',
}

function buildActiveProfileItems(onboarding) {
  if (!onboarding || onboarding?.onboarding_status !== 'completed') return []
  const config = onboarding?.product_configuration || {}
  const items = []

  const primaryLabel = PRIMARY_USE_CASE_LABELS[onboarding?.primary_use_case]
  if (primaryLabel) items.push(`Startprofiel: ${primaryLabel}`)

  if (config.inventory_tracking_level === 'quantity') items.push('Voorraad met aantallen')
  else if (config.inventory_tracking_level === 'presence') items.push('Voorraad op aanwezigheid')

  if (config.location_tracking_level === 'exact') items.push('Exacte locaties')
  else if (config.location_tracking_level === 'global') items.push('Globale locaties')

  if (config.shopping_enabled) items.push('Winkelen')
  if (config.almost_out_enabled) items.push('Bijna op')
  if (config.almost_out_notifications_enabled) items.push('Bijna-op meldingen')
  if (config.receipt_processing_enabled) items.push('Kassabonnen')
  if (config.unpacking_enabled) items.push('Uitpakken')
  if (config.recipes_enabled) items.push('Gerechten')

  const usageMode = String(onboarding?.household_usage_mode || '')
  if (usageMode === 'together') items.push('Huishouden samen gebruiken')
  if (usageMode === 'alone') items.push('Huishouden alleen gebruiken')

  return items
}

export default function SettingsPage() {
  const context = readStoredAuthContext()
  const [onboarding, setOnboarding] = useState(() => readHouseholdOnboarding(context))
  const [primaryColor, setPrimaryColor] = useState(() => readPrimaryColorPreference())
  const [primaryColorDraft, setPrimaryColorDraft] = useState(() => readPrimaryColorPreference())
  const [primaryColorError, setPrimaryColorError] = useState('')
  const navigation = buildSettingsNavigation({ onboarding })
  const activeProfileItems = buildActiveProfileItems(onboarding)

  useEffect(() => {
    let cancelled = false

    async function refreshProductConfiguration() {
      if (context?.context_type !== 'regular') return
      try {
        const nextOnboarding = await fetchHouseholdOnboarding(context, { force: true })
        if (!cancelled) setOnboarding(nextOnboarding)
      } catch {
        // AuthGuard/SettingsGuard remain authoritative. Falling back to the legacy
        // catalogue is safer than accidentally hiding settings on a read failure.
      }
    }

    refreshProductConfiguration()
    return () => {
      cancelled = true
    }
  }, [context?.user_id, context?.active_household_id, context?.context_type])

  function applyPrimaryColor() {
    try {
      const applied = writePrimaryColorPreference(primaryColorDraft)
      setPrimaryColor(applied)
      setPrimaryColorDraft(applied)
      setPrimaryColorError('')
    } catch (error) {
      setPrimaryColorError(error?.message || 'De hoofdkleur kon niet worden toegepast.')
    }
  }

  function restorePrimaryColor() {
    const applied = resetPrimaryColorPreference()
    setPrimaryColor(applied)
    setPrimaryColorDraft(applied)
    setPrimaryColorError('')
  }

  function getTileStyle(disabled = false) {
    return {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px',
      border: `1px solid ${disabled ? 'var(--color-ui-primary)' : '#dfe4ea'}`, borderRadius: '12px',
      color: disabled ? 'var(--color-ui-primary)' : 'inherit', textDecoration: 'none',
      background: disabled ? '#d8f3dc' : '#ffffff', cursor: disabled ? 'not-allowed' : 'pointer',
      boxShadow: disabled ? 'none' : undefined, opacity: 1, width: '100%', boxSizing: 'border-box',
    }
  }

  function tileLink(tile) {
    return (
      <Link
        to={tile.to}
        style={getTileStyle(false)}
        data-testid={`settings-tile-${tile.key}`}
        data-settings-scope={tile.scope}
      >
        <div>
          <div style={{ fontWeight: 600 }}>{tile.title}</div>
          <div style={{ color: '#667085', fontSize: '14px' }}>{tile.description}</div>
        </div>
        <div aria-hidden="true">→</div>
      </Link>
    )
  }

  function renderTile(tile) {
    const link = tileLink(tile)
    if (!tile.permission) return <div key={tile.key}>{link}</div>

    return (
      <AuthorizedControl
        key={tile.key}
        permission={tile.permission}
        className="rz-authorized-control--tile"
      >
        {link}
      </AuthorizedControl>
    )
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div
          style={{ display: 'grid', gap: '24px' }}
          data-testid="settings-page"
          data-settings-mode={navigation.mode}
        >
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Instellingen</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              {navigation.mode === 'dynamic'
                ? 'Je ziet instellingen die passen bij de mogelijkheden die voor dit huishouden actief zijn.'
                : 'Beheer hier je persoonlijke voorkeuren en de inrichting van je huishouden.'}
            </p>
          </div>

          <section
            data-testid="settings-primary-color"
            style={{
              display: 'grid',
              gap: 12,
              padding: '14px 16px',
              border: '1px solid #dfe4ea',
              borderRadius: 12,
              background: '#ffffff',
            }}
          >
            <div>
              <h3 style={{ margin: '0 0 4px 0', fontSize: '17px' }}>Weergave</h3>
              <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>
                Donkergroene hoofdkleur voor headers, primaire knoppen, tabelkoppen, focus en actieve accenten.
                De standaardkleur is {DEFAULT_PRIMARY_COLOR}; deze voorkeur geldt op dit apparaat.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'end', flexWrap: 'wrap' }}>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>Kleur kiezen</span>
                <input
                  type="color"
                  value={normalizePrimaryColor(primaryColorDraft) || primaryColor}
                  onChange={(event) => {
                    setPrimaryColorDraft(event.target.value.toUpperCase())
                    setPrimaryColorError('')
                  }}
                  aria-label="Donkergroene hoofdkleur kiezen"
                  data-testid="settings-primary-color-picker"
                  style={{ width: 52, height: 42, padding: 2, cursor: 'pointer' }}
                />
              </label>
              <label style={{ display: 'grid', gap: 6, minWidth: 150 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>Hexkleur</span>
                <input
                  className="rz-input"
                  value={primaryColorDraft}
                  onChange={(event) => {
                    setPrimaryColorDraft(event.target.value.toUpperCase())
                    setPrimaryColorError('')
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      applyPrimaryColor()
                    }
                  }}
                  inputMode="text"
                  maxLength={7}
                  aria-label="Hexkleur hoofdkleur"
                  data-testid="settings-primary-color-hex"
                />
              </label>
              <Button type="button" variant="primary" onClick={applyPrimaryColor} data-testid="settings-primary-color-apply">
                Toepassen
              </Button>
              <Button type="button" variant="secondary" onClick={restorePrimaryColor} data-testid="settings-primary-color-reset">
                Standaard herstellen
              </Button>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 14 }}>
              <span>Actief:</span>
              <span
                data-testid="settings-primary-color-active"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  minHeight: 30,
                  padding: '4px 10px',
                  borderRadius: 8,
                  background: primaryColor,
                  color: '#FFFFFF',
                  fontWeight: 600,
                }}
              >
                {primaryColor}
              </span>
            </div>
            {primaryColorError ? (
              <div role="alert" style={{ color: '#b42318', fontSize: 14 }} data-testid="settings-primary-color-error">
                {primaryColorError}
              </div>
            ) : null}
          </section>

          {context?.context_type === 'regular' && activeProfileItems.length ? (
            <section
              data-testid="settings-active-profile"
              style={{
                display: 'grid',
                gap: 10,
                padding: '14px 16px',
                border: '1px solid #dfe4ea',
                borderRadius: 12,
                background: '#ffffff',
              }}
            >
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '17px' }}>Jouw Inhuis</h3>
                <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>
                  Dit is de inrichting die voor dit huishouden actief is. De instellingen hieronder sluiten hierop aan.
                </p>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {activeProfileItems.map((item) => (
                  <span
                    key={item}
                    style={{
                      padding: '6px 10px',
                      borderRadius: 999,
                      background: '#eef6f0',
                      border: '1px solid #b8d9c1',
                      fontSize: '14px',
                    }}
                  >
                    {item}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {navigation.sections.map((section) => (
            <section
              key={section.key}
              data-testid={`settings-section-${section.key}`}
              style={{ display: 'grid', gap: '12px' }}
            >
              <div>
                <h3 style={{ margin: '0 0 4px 0', fontSize: '17px' }}>{section.title}</h3>
                <p style={{ margin: 0, color: '#667085', fontSize: '14px' }}>{section.description}</p>
              </div>
              <div style={{ display: 'grid', gap: '12px' }}>
                {section.tiles.map(renderTile)}
              </div>
            </section>
          ))}
        </div>
      </Card>
    </AppShell>
  )
}
