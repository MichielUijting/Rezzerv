import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import { fetchPrivacyDataSharingSettings, updatePrivacyDataSharingSettings } from './services/privacyDataSharingService'

const DEFAULT_SETTINGS = {
  share_with_retailers: false,
  share_with_partners: false,
  allow_smart_features: false,
  allow_statistics: false,
  allow_personal_offers: false,
  allow_loyalty_import: false,
}

const SETTING_ROWS = [
  { key: 'share_with_retailers', title: 'Data delen met winkels', description: 'Sta toe dat winkelketens gegevens ontvangen wanneer jij daar expliciet gebruik van wilt maken.' },
  { key: 'share_with_partners', title: 'Data delen met servicepartners', description: 'Sta toekomstige koppelingen met serviceleveranciers alleen toe wanneer jij dat zelf inschakelt.' },
  { key: 'allow_smart_features', title: 'Data gebruiken voor slimme functies', description: 'Deze optie vormt later de basis voor Smart-licenties en andere slimme aanbevelingen.' },
  { key: 'allow_statistics', title: 'Data gebruiken voor statistiek en onderzoek', description: 'Gebruik alleen geaggregeerde gegevens voor analyses en productverbetering.' },
  { key: 'allow_personal_offers', title: 'Persoonlijke aanbiedingen toestaan', description: 'Sta gepersonaliseerde aanbiedingen pas toe wanneer jij deze expliciet wilt ontvangen.' },
  { key: 'allow_loyalty_import', title: 'Automatische koppelingen met klantkaarten toestaan', description: 'Sta automatische import uit klantkaarten alleen toe wanneer jij daar toestemming voor geeft.' },
]

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export default function SettingsPrivacyDataSharingPage() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const dismissTimerRef = useRef(null)

  useDismissOnComponentClick([() => setMessage(''), () => setError('')], Boolean(message || error))

  const snapshot = useMemo(() => stableStringify(settings), [settings])
  const isDirty = !isLoading && !!lastSavedSnapshot && snapshot !== lastSavedSnapshot
  const blocker = useBlocker(isDirty)

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      setError('')
      try {
        const payload = await fetchPrivacyDataSharingSettings()
        if (!active) return
        const nextSettings = { ...DEFAULT_SETTINGS, ...payload }
        setSettings(nextSettings)
        setLastSavedSnapshot(stableStringify(nextSettings))
      } catch (loadError) {
        if (!active) return
        setSettings(DEFAULT_SETTINGS)
        setLastSavedSnapshot(stableStringify(DEFAULT_SETTINGS))
        setError(loadError?.message || 'Privacy-instellingen konden niet worden geladen.')
      } finally {
        if (active) setIsLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (blocker.state === 'blocked') setShowLeaveModal(true)
  }, [blocker.state])

  useEffect(() => {
    function handleBeforeUnload(event) {
      if (!isDirty) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [isDirty])

  useEffect(() => () => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
  }, [])

  function queueMessage(text) {
    setError('')
    setMessage(text)
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
    dismissTimerRef.current = setTimeout(() => setMessage(''), 3000)
  }

  function updateSetting(key, checked) {
    setSettings((current) => ({ ...current, [key]: checked }))
  }

  async function handleSave() {
    setIsSaving(true)
    setError('')
    setMessage('')
    try {
      const payload = await updatePrivacyDataSharingSettings(settings)
      const nextSettings = { ...DEFAULT_SETTINGS, ...payload }
      setSettings(nextSettings)
      setLastSavedSnapshot(stableStringify(nextSettings))
      queueMessage(payload?.settings_message || 'Privacy- en datadeelrechten opgeslagen.')
      return true
    } catch (saveError) {
      setError(saveError?.message || 'Privacy-instellingen konden niet worden opgeslagen.')
      return false
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveAndLeave() {
    const ok = await handleSave()
    if (!ok) return
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  function handleStay() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.reset()
  }

  function handleLeaveWithoutSaving() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '20px' }} data-testid="settings-privacy-data-sharing-page">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Privacy &amp; Datadeling</h2>
              <p style={{ margin: 0, color: '#667085' }}>Beheer hier per gebruiker welke data mag worden gebruikt. Alles staat standaard uit en alleen jij kunt dit voor jezelf wijzigen.</p>
            </div>
            <Link to="/instellingen" style={{ textDecoration: 'none', fontWeight: 600 }}>← Terug naar instellingen</Link>
          </div>

          {(message || error) ? (
            <div className={error ? 'rz-inline-feedback rz-inline-feedback--error' : 'rz-inline-feedback rz-inline-feedback--success'}>
              {error || message}
            </div>
          ) : null}

          {isLoading ? <div>Privacy-instellingen laden…</div> : (
            <>
              <div style={{ display: 'grid', gap: '12px' }}>
                {SETTING_ROWS.map((item) => (
                  <label key={item.key} style={{ display: 'grid', gridTemplateColumns: '24px 1fr', gap: '12px', alignItems: 'start', padding: '14px 16px', border: '1px solid #dfe4ea', borderRadius: '12px', background: '#fff' }}>
                    <input
                      type="checkbox"
                      checked={Boolean(settings[item.key])}
                      onChange={(event) => updateSetting(item.key, event.target.checked)}
                      disabled={isSaving}
                      data-testid={`privacy-setting-${item.key}`}
                      style={{ marginTop: '2px', accentColor: '#1f6f43', width: '18px', height: '18px', cursor: isSaving ? 'not-allowed' : 'pointer' }}
                    />
                    <span>
                      <strong>{item.title}</strong><br />
                      <small style={{ color: '#667085' }}>{item.description}</small>
                    </span>
                  </label>
                ))}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <Button onClick={handleSave} disabled={isSaving || !isDirty} data-testid="privacy-settings-save">
                  {isSaving ? 'Opslaan…' : 'Opslaan'}
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>

      {showLeaveModal ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-privacy-settings-title" data-testid="privacy-warning-dialog">
            <h3 id="leave-privacy-settings-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
            <p className="rz-modal-text">Je hebt privacy-instellingen aangepast die nog niet zijn opgeslagen.</p>
            <div className="rz-modal-actions">
              <Button variant="secondary" onClick={handleStay}>Blijven</Button>
              <Button variant="secondary" onClick={handleLeaveWithoutSaving}>Niet opslaan</Button>
              <Button onClick={handleSaveAndLeave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
