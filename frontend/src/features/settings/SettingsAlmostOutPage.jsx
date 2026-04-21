import { useEffect, useMemo, useRef, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import Input from '../../ui/Input'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'
import {
  ALMOST_OUT_POLICY_OPTIONS,
  ALMOST_OUT_POLICY_MODES,
  fetchAlmostOutSettings,
  saveAlmostOutSettings,
} from './services/almostOutSettingsService'

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export default function SettingsAlmostOutPage() {
  const [predictionEnabled, setPredictionEnabled] = useState(false)
  const [predictionDays, setPredictionDays] = useState('7')
  const [policyMode, setPolicyMode] = useState(ALMOST_OUT_POLICY_MODES.ADVISORY)
  const [canEdit, setCanEdit] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const dismissTimerRef = useRef(null)

  useDismissOnComponentClick([() => setSaveMessage(''), () => setSaveError('')], Boolean(saveMessage || saveError))

  useEffect(() => {
    let cancelled = false
    fetchAlmostOutSettings()
      .then((settings) => {
        if (cancelled) return
        setPredictionEnabled(Boolean(settings.predictionEnabled))
        setPredictionDays(String(settings.predictionDays ?? 0))
        setPolicyMode(settings.policyMode || ALMOST_OUT_POLICY_MODES.ADVISORY)
        setCanEdit(Boolean(settings.isHouseholdAdmin))
      })
      .catch((error) => {
        if (cancelled) return
        setSaveError(error?.message || 'Almost-out instellingen konden niet worden geladen.')
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const currentSettings = useMemo(() => ({
    predictionEnabled: Boolean(predictionEnabled),
    predictionDays: Math.max(0, Number(predictionDays) || 0),
    policyMode,
  }), [predictionEnabled, predictionDays, policyMode])
  const currentSnapshot = useMemo(() => stableStringify(currentSettings), [currentSettings])
  const isDirty = !isLoading && !!lastSavedSnapshot && currentSnapshot !== lastSavedSnapshot
  const blocker = useBlocker(isDirty)

  useEffect(() => {
    if (!isLoading && !lastSavedSnapshot) {
      setLastSavedSnapshot(currentSnapshot)
    }
  }, [isLoading, lastSavedSnapshot, currentSnapshot])

  useEffect(() => {
    if (saveMessage && isDirty) setSaveMessage('')
  }, [isDirty, saveMessage])

  useEffect(() => () => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
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

  function queueSuccessMessage(text) {
    setSaveError('')
    setSaveMessage(text)
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
    dismissTimerRef.current = setTimeout(() => setSaveMessage(''), 3000)
  }

  async function handleSave() {
    setIsSaving(true)
    setSaveError('')
    try {
      const saved = await saveAlmostOutSettings({
        predictionEnabled,
        predictionDays: Math.max(0, Number(predictionDays) || 0),
        policyMode,
      })
      const nextSettings = {
        predictionEnabled: Boolean(saved.predictionEnabled),
        predictionDays: Math.max(0, Number(saved.predictionDays) || 0),
        policyMode: saved.policyMode || ALMOST_OUT_POLICY_MODES.ADVISORY,
      }
      setPredictionEnabled(nextSettings.predictionEnabled)
      setPredictionDays(String(nextSettings.predictionDays))
      setPolicyMode(nextSettings.policyMode)
      setLastSavedSnapshot(stableStringify(nextSettings))
      queueSuccessMessage('Opgeslagen')
      return true
    } catch (error) {
      setSaveError(error?.message || 'Opslaan is niet gelukt.')
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

  function handleLeaveWithoutSaving() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  function handleStay() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.reset()
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div data-testid="settings-almost-out-page">
        <Card>
          <div style={{ display: 'grid', gap: '18px' }}>
            <div>
              <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Bijna op voorspelling</h2>
              <p style={{ margin: 0, color: '#667085' }}>
                Stel hier huishoudbreed in of Rezzerv artikelen al op <strong>Bijna op</strong> zet wanneer verwacht wordt dat ze binnen een aantal dagen uit voorraad raken.
              </p>
              {!isLoading && !canEdit ? (
                <p style={{ margin: '8px 0 0 0', color: '#b54708', fontWeight: 600 }}>
                  Alleen de beheerder van het huishouden kan deze instelling wijzigen.
                </p>
              ) : null}
            </div>

            <div className="rz-automation-setting-card">
              <div className="rz-automation-setting-copy">
                <div className="rz-automation-setting-title">Gebruik voorspelde uitputting</div>
                <div className="rz-automation-setting-text">Rezzerv gebruikt de gemiddelde tijd tussen aankopen per huishoudartikel om te schatten wanneer de voorraad op raakt.</div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#0f172a', fontWeight: 600 }}>
                <input
                  type="checkbox"
                  style={{ accentColor: '#1A3E2B', width: 16, height: 16 }}
                  checked={predictionEnabled}
                  onChange={(event) => {
                    setSaveMessage('')
                    setSaveError('')
                    setPredictionEnabled(event.target.checked)
                  }}
                  disabled={!canEdit || isSaving}
                  data-testid="almost-out-prediction-enabled"
                />
                Ingeschakeld
              </label>
            </div>

            <div style={{ display: 'grid', gap: '16px', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}>
              <Input
                label="Aantal dagen vooruitkijken"
                type="number"
                min="0"
                step="1"
                value={predictionDays}
                onChange={(event) => {
                  setSaveMessage('')
                  setSaveError('')
                  setPredictionDays(event.target.value)
                }}
                disabled={!canEdit || isSaving}
                data-testid="almost-out-prediction-days"
                placeholder="Bijvoorbeeld: 7"
              />

              <label className="rz-input-field">
                <div className="rz-label">Regel prioriteit</div>
                <select
                  className="rz-input"
                  value={policyMode}
                  onChange={(event) => {
                    setSaveMessage('')
                    setSaveError('')
                    setPolicyMode(event.target.value)
                  }}
                  disabled={!canEdit || isSaving}
                  data-testid="almost-out-policy-mode"
                >
                  {ALMOST_OUT_POLICY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <Card>
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ fontWeight: 600 }}>Toelichting beleidsmodi</div>
                {ALMOST_OUT_POLICY_OPTIONS.map((option) => (
                  <div key={option.value} style={{ display: 'grid', gap: 4 }}>
                    <div style={{ fontWeight: 600 }}>{option.label}</div>
                    <div style={{ color: '#667085' }}>{option.description}</div>
                  </div>
                ))}
              </div>
            </Card>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
              <div />
              <div className="rz-save-cluster">
                {(saveMessage || saveError) ? (
                  <div
                    role="status"
                    aria-live="polite"
                    data-save-status={saveError ? 'error' : 'saved'}
                    className={saveError ? 'rz-inline-feedback rz-inline-feedback--error rz-save-feedback rz-save-feedback-overlay' : 'rz-inline-feedback rz-inline-feedback--success rz-save-feedback rz-save-feedback-overlay'}
                  >
                    {saveError || saveMessage}
                  </div>
                ) : null}
                <Button onClick={handleSave} disabled={isSaving || !canEdit || isLoading} data-testid="almost-out-settings-save">
                  {isSaving ? 'Opslaan…' : 'Opslaan'}
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {showLeaveModal ? (
          <div className="rz-modal-backdrop" role="presentation">
            <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-almost-out-settings-title">
              <h3 id="leave-almost-out-settings-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
              <p className="rz-modal-text">Je hebt wijzigingen aangebracht die nog niet zijn opgeslagen.</p>
              <div className="rz-modal-actions">
                <Button variant="secondary" onClick={handleStay}>Blijven</Button>
                <Button variant="secondary" onClick={handleLeaveWithoutSaving}>Niet opslaan</Button>
                <Button onClick={handleSaveAndLeave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan en doorgaan'}</Button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  )
}
