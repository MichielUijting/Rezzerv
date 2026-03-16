import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import {
  STORE_IMPORT_SIMPLIFICATION_LEVELS,
  getStoreImportSimplificationLabel,
  getStoreImportSimplificationSettings,
  saveStoreImportSimplificationSettings,
} from './services/storeImportSimplificationService'

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }
  return JSON.stringify(value)
}

export default function SettingsStoreImportPage() {
  const [level, setLevel] = useState('gebalanceerd')
  const [canEdit, setCanEdit] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const dismissTimerRef = useRef(null)
  const currentSnapshot = useMemo(() => stableStringify({ level }), [level])
  const isDirty = !isLoading && !!lastSavedSnapshot && currentSnapshot !== lastSavedSnapshot
  const blocker = useBlocker(isDirty)

  useEffect(() => {
    let active = true
    async function load() {
      setIsLoading(true)
      setLoadError('')
      try {
        const data = await getStoreImportSimplificationSettings()
        if (!active) return
        const nextLevel = data?.store_import_simplification_level || 'gebalanceerd'
        setLevel(nextLevel)
        setCanEdit(Boolean(data?.can_edit_store_import_simplification_level))
        setLastSavedSnapshot(stableStringify({ level: nextLevel }))
      } catch (error) {
        if (!active) return
        setLoadError(error?.message || 'Instellingen konden niet worden geladen.')
      } finally {
        if (active) setIsLoading(false)
      }
    }
    load()
    return () => { active = false }
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

  useEffect(() => () => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
  }, [])

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
      const saved = await saveStoreImportSimplificationSettings(level)
      const nextLevel = saved?.store_import_simplification_level || level
      setLevel(nextLevel)
      setCanEdit(Boolean(saved?.can_edit_store_import_simplification_level))
      setLastSavedSnapshot(stableStringify({ level: nextLevel }))
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

  function handleStay() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.reset()
  }

  function handleLeaveWithoutSaving() {
    setShowLeaveModal(false)
    if (blocker.state === 'blocked') blocker.proceed()
  }

  const selectedLevel = STORE_IMPORT_SIMPLIFICATION_LEVELS.find((option) => option.value === level)

  return (
    <AppShell title="Instellingen" showExit={false}>
      <div data-testid="store-import-page">
      <Card>
        <div style={{ display: 'grid', gap: '20px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Winkelimport</h2>
            <p style={{ margin: 0, color: '#667085' }}>
              Deze instelling geldt voor het hele huishouden. Alleen de beheerder van het huishouden kan het vereenvoudigingsniveau wijzigen.
            </p>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}><Link to="/instellingen" data-testid="store-import-back-link" style={{ color: '#0f5b32', textDecoration: 'none', fontWeight: 600 }}>← Terug naar instellingen</Link></div>

          {isLoading ? <div>Instellingen laden…</div> : (
            <>
              {loadError ? <div className="rz-inline-feedback rz-inline-feedback--error">{loadError}</div> : null}
              <div className="rz-automation-setting-card" style={{ alignItems: 'stretch' }}>
                <div className="rz-automation-setting-copy">
                  <div className="rz-automation-setting-title">Vereenvoudigingsniveau winkelimport</div>
                  <div className="rz-automation-setting-text">
                    Kies hoeveel van de winkelimport automatisch mag worden voorbereid. Huidige stand: <strong>{getStoreImportSimplificationLabel(level)}</strong>.
                  </div>
                </div>
                <div style={{ minWidth: '240px', display: 'grid', gap: '10px' }}>
                  <select
                    data-testid="store-import-level-select"
                    value={level}
                    onChange={(event) => {
                      setSaveError('')
                      setSaveMessage('')
                      setLevel(event.target.value)
                    }}
                    disabled={!canEdit || isSaving}
                    style={{ width: '100%' }}
                  >
                    {STORE_IMPORT_SIMPLIFICATION_LEVELS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {!canEdit ? (
                    <div className="rz-inline-feedback rz-inline-feedback--warning">Alleen de beheerder van het huishouden kan dit wijzigen.</div>
                  ) : null}
                </div>
              </div>

              {selectedLevel ? (
                <div style={{ display: 'grid', gap: '10px' }}>
                  <div style={{ fontWeight: 600 }}>Uitleg van het gekozen niveau</div>
                  <div style={{ padding: '14px 16px', border: '1px solid #dfe4ea', borderRadius: '12px', color: '#475467' }}>{selectedLevel.description}</div>
                </div>
              ) : null}

              <div style={{ display: 'grid', gap: '10px' }}>
                <div style={{ fontWeight: 600 }}>Niveaus</div>
                <div style={{ display: 'grid', gap: '10px' }}>
                  {STORE_IMPORT_SIMPLIFICATION_LEVELS.map((option) => (
                    <div key={option.value} style={{ padding: '14px 16px', border: '1px solid #dfe4ea', borderRadius: '12px' }}>
                      <div style={{ fontWeight: 600 }}>{option.label}</div>
                      <div style={{ color: '#667085', fontSize: '14px' }}>{option.description}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div />
                <div className="rz-save-cluster">
                  {(saveMessage || saveError) ? (
                    <div className={saveError ? 'rz-inline-feedback rz-inline-feedback--error rz-save-feedback rz-save-feedback-overlay' : 'rz-inline-feedback rz-inline-feedback--success rz-save-feedback rz-save-feedback-overlay'}>
                      {saveError || saveMessage}
                    </div>
                  ) : null}
                  <Button onClick={handleSave} disabled={isSaving || !canEdit}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
                </div>
              </div>
            </>
          )}
        </div>
      </Card>

      {showLeaveModal ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-store-import-settings-title" data-testid="warning-dialog">
            <h3 id="leave-store-import-settings-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
            <p className="rz-modal-text">Je hebt wijzigingen aangebracht die nog niet zijn opgeslagen.</p>
            <div className="rz-modal-actions">
              <Button variant="secondary" onClick={handleStay} data-testid="warning-cancel">Blijven</Button>
              <Button variant="secondary" onClick={handleLeaveWithoutSaving} data-testid="warning-confirm">Niet opslaan</Button>
              <Button onClick={handleSaveAndLeave} disabled={isSaving || !canEdit}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      ) : null}
      </div>
    </AppShell>
  )
}
