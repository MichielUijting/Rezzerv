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
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const dismissTimerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    fetchHouseholdAutomationSettings()
      .then((settings) => {
        if (cancelled) return
        setMode(settings.mode || HOUSEHOLD_AUTO_CONSUME_MODES.NONE)
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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
      <Card>
        <div style={{ display: 'grid', gap: '18px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Huishoudautomatisering</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Deze instelling geldt voor het hele huishouden. Kies hoe Rezzerv verbruiksartikelen automatisch moet afboeken bij een nieuwe aankoop.
            </p>
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
                value={mode}
                onChange={(event) => {
                  setSaveMessage('')
                  setSaveError('')
                  setMode(event.target.value)
                }}
              >
                <option value={HOUSEHOLD_AUTO_CONSUME_MODES.NONE}>Geen automatische afboeking</option>
                <option value={HOUSEHOLD_AUTO_CONSUME_MODES.CONSUME_PURCHASED_QUANTITY}>Boek hetzelfde aantal af als gekocht</option>
                <option value={HOUSEHOLD_AUTO_CONSUME_MODES.CONSUME_ALL_EXISTING}>Boek bestaande voorraad eerst volledig af tot 0</option>
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
              <Button onClick={handleSave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
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
              <Button onClick={handleSaveAndLeave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
