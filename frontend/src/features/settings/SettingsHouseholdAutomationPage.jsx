import { useEffect, useMemo, useRef, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import {
  fetchHouseholdAutomationSettings,
  saveHouseholdAutomationSettings,
  HOUSEHOLD_AUTO_CONSUME_MODES,
} from './services/householdAutomationService'
import { sortOptionObjects } from '../../ui/sorting'
import useDismissOnComponentClick from '../../lib/useDismissOnComponentClick.js'

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`
  }

  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }

  return JSON.stringify(value)
}

export default function SettingsHouseholdAutomationPage() {
  const [mode, setMode] = useState(HOUSEHOLD_AUTO_CONSUME_MODES.NONE)
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
    fetchHouseholdAutomationSettings()
      .then((settings) => {
        if (cancelled) return
        setMode(settings.mode || HOUSEHOLD_AUTO_CONSUME_MODES.NONE)
        setCanEdit(Boolean(settings.isHouseholdAdmin))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const automationOptions = useMemo(() => sortOptionObjects([
    { value: HOUSEHOLD_AUTO_CONSUME_MODES.NONE, label: 'Geen automatische afboeking' },
    { value: HOUSEHOLD_AUTO_CONSUME_MODES.CONSUME_ALL_EXISTING, label: 'Boek bestaande voorraad eerst volledig af tot 0' },
    { value: HOUSEHOLD_AUTO_CONSUME_MODES.CONSUME_PURCHASED_QUANTITY, label: 'Boek hetzelfde aantal af als gekocht' },
  ]), [])
  const currentSettings = useMemo(() => ({ mode }), [mode])
  const currentSnapshot = useMemo(() => stableStringify(currentSettings), [currentSettings])
  const isDirty = !isLoading && !!lastSavedSnapshot && currentSnapshot !== lastSavedSnapshot
  const blocker = useBlocker(isDirty)

  useEffect(() => {
    if (!isLoading && !lastSavedSnapshot) {
      setLastSavedSnapshot(currentSnapshot)
    }
  }, [isLoading, lastSavedSnapshot, currentSnapshot])

  useEffect(() => {
    if (saveMessage && isDirty) {
      setSaveMessage('')
    }
  }, [isDirty, saveMessage])

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) {
        clearTimeout(dismissTimerRef.current)
      }
    }
  }, [])

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowLeaveModal(true)
    }
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
      const saved = await saveHouseholdAutomationSettings({ mode })
      const savedSettings = {
        mode: saved?.mode || mode,
      }
      setMode(savedSettings.mode)
      setLastSavedSnapshot(stableStringify(savedSettings))
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
    if (blocker.state === 'blocked') {
      blocker.proceed()
    }
  }

  function handleLeaveWithoutSaving() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') {
      blocker.proceed()
    }
  }

  function handleStay() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') {
      blocker.reset()
    }
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div data-testid="settings-page">
        <Card>
        <div style={{ display: 'grid', gap: '18px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Huishoudautomatisering</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Deze instelling geldt voor het hele huishouden. Kies hoe Rezzerv verbruiksartikelen automatisch moet afboeken bij een nieuwe aankoop.
            </p>
            {!isLoading && !canEdit ? (
              <p style={{ margin: '8px 0 0 0', color: '#b54708', fontWeight: 600 }}>
                Alleen de beheerder van het huishouden kan deze instelling wijzigen.
              </p>
            ) : null}
          </div>

          <div className="rz-automation-setting-card">
            <div className="rz-automation-setting-copy">
              <div className="rz-automation-setting-title">Automatische afboeking verbruiksartikelen</div>
              <div className="rz-automation-setting-text">Alleen voor verbruiksartikelen. De gekozen strategie wordt zichtbaar vastgelegd in Historie en Analyse.</div>
            </div>
            <label className="rz-article-automation-field" style={{ minWidth: '340px' }}>
              <span className="rz-article-automation-label">Strategie</span>
              <select
                className="rz-article-automation-select"
                data-testid="household-automation-toggle"
                value={mode}
                onChange={(event) => {
                  setSaveMessage('')
                  setSaveError('')
                  setMode(event.target.value)
                }}
                disabled={!canEdit || isSaving}
              >
                {automationOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>

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
              <Button onClick={handleSave} disabled={isSaving || !canEdit} data-testid="household-automation-save">{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
        </Card>
      {showLeaveModal ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-household-automation-title">
            <h3 id="leave-household-automation-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
            <p className="rz-modal-text">Je hebt wijzigingen aangebracht die nog niet zijn opgeslagen.</p>
            <div className="rz-modal-actions">
              <Button variant="secondary" onClick={handleStay}>Blijven</Button>
              <Button variant="secondary" onClick={handleLeaveWithoutSaving}>Niet opslaan</Button>
              <Button onClick={handleSaveAndLeave} disabled={isSaving || !canEdit}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      ) : null}
      </div>
    </AppShell>
  )
}
