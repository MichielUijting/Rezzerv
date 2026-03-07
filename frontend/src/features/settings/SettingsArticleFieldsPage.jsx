import { useEffect, useMemo, useRef, useState } from 'react'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { useArticleFieldVisibility } from '../articles/hooks/useArticleFieldVisibility'
import { ARTICLE_TABS } from '../articles/config/articleFieldConstants'
import { getFieldsByTabAndGroup } from '../articles/config/articleFieldHelpers'
import FieldVisibilitySection from './components/FieldVisibilitySection'

const TAB_LABELS = {
  [ARTICLE_TABS.OVERVIEW]: 'Overzicht',
  [ARTICLE_TABS.STOCK]: 'Voorraad',
  [ARTICLE_TABS.LOCATIONS]: 'Locaties',
  [ARTICLE_TABS.HISTORY]: 'Historie',
  [ARTICLE_TABS.ANALYTICS]: 'Analyse',
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`
  }

  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`
  }

  return JSON.stringify(value)
}

export default function SettingsArticleFieldsPage() {
  const { visibilityMap, alwaysVisibleKeys, isLoading, isSaving, error, toggleFieldVisibility, resetToDefault, showAllFields, saveVisibility } = useArticleFieldVisibility()
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const dismissTimerRef = useRef(null)
  const bypassLeaveGuardRef = useRef(false)
  const pendingBrowserBackRef = useRef(false)

  const groupedFieldsByTab = useMemo(() => ({
    [ARTICLE_TABS.OVERVIEW]: getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW),
    [ARTICLE_TABS.STOCK]: getFieldsByTabAndGroup(ARTICLE_TABS.STOCK),
    [ARTICLE_TABS.LOCATIONS]: {},
    [ARTICLE_TABS.HISTORY]: {},
    [ARTICLE_TABS.ANALYTICS]: {},
  }), [])

  const currentSnapshot = useMemo(() => stableStringify(visibilityMap || {}), [visibilityMap])
  const isDirty = hasUnsavedChanges || (!isLoading && !!lastSavedSnapshot && currentSnapshot !== lastSavedSnapshot)

  useEffect(() => {
    if (!isLoading && !lastSavedSnapshot) {
      setLastSavedSnapshot(currentSnapshot)
      setHasUnsavedChanges(false)
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
    function handleBeforeUnload(event) {
      if (!isDirty || bypassLeaveGuardRef.current) return
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [isDirty])

  useEffect(() => {
    function handlePopState() {
      if (!isDirty || bypassLeaveGuardRef.current) {
        return
      }

      pendingBrowserBackRef.current = true
      setShowLeaveModal(true)
      window.history.go(1)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [isDirty])

  function queueSuccessMessage(text) {
    setSaveError('')
    setSaveMessage(text)
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current)
    dismissTimerRef.current = setTimeout(() => setSaveMessage(''), 3000)
  }

  async function handleSave() {
    setSaveError('')
    const result = await saveVisibility()

    if (result.ok) {
      const savedSnapshot = stableStringify(result.data || visibilityMap || {})
      setLastSavedSnapshot(savedSnapshot)
      setHasUnsavedChanges(false)
      queueSuccessMessage('Opgeslagen')
      return true
    }

    setSaveError(result.error?.message || 'Opslaan is niet gelukt.')
    return false
  }

  async function handleSaveAndLeave() {
    const ok = await handleSave()
    if (!ok) return
    bypassLeaveGuardRef.current = true
    setShowLeaveModal(false)
    if (pendingBrowserBackRef.current) {
      pendingBrowserBackRef.current = false
      window.history.back()
    }
  }

  function handleLeaveWithoutSaving() {
    bypassLeaveGuardRef.current = true
    setShowLeaveModal(false)
    if (pendingBrowserBackRef.current) {
      pendingBrowserBackRef.current = false
      window.history.back()
    }
  }

  function handleResetDefaults() {
    setSaveError('')
    setSaveMessage('')
    setHasUnsavedChanges(true)
    resetToDefault()
  }

  function handleShowAll() {
    setSaveError('')
    setSaveMessage('')
    setHasUnsavedChanges(true)
    showAllFields()
  }

  return (
    <AppShell title="Instellingen" showExit={false}>
      <Card>
        <div style={{ display: 'grid', gap: '20px' }}>
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>Artikeldetails → Veldzichtbaarheid</h2>
            <p style={{ margin: 0, color: '#667085' }}>Bepaal welke velden zichtbaar zijn in het artikeldetailscherm. Velden die altijd nodig zijn, blijven zichtbaar.</p>
          </div>

          {isLoading ? <div>Instellingen laden…</div> : (
            <>
              {error ? <div className="rz-inline-feedback rz-inline-feedback--warning">De standaardweergave is geladen omdat voorkeuren niet konden worden opgehaald.</div> : null}
              <FieldVisibilitySection title={TAB_LABELS.overview} tabKey={ARTICLE_TABS.OVERVIEW} groupedFields={groupedFieldsByTab[ARTICLE_TABS.OVERVIEW]} visibilityMap={visibilityMap} alwaysVisibleKeys={alwaysVisibleKeys} onToggle={(tabKey, fieldKey) => { setHasUnsavedChanges(true); toggleFieldVisibility(tabKey, fieldKey) }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <Button variant="secondary" onClick={handleResetDefaults} disabled={isSaving}>Herstel standaardweergave</Button>
                  <Button variant="secondary" onClick={handleShowAll} disabled={isSaving}>Alles tonen</Button>
                </div>
                <div className="rz-save-cluster">
                  {(saveMessage || saveError) ? (
                    <div className={saveError ? 'rz-inline-feedback rz-inline-feedback--error rz-save-feedback rz-save-feedback-overlay' : 'rz-inline-feedback rz-inline-feedback--success rz-save-feedback rz-save-feedback-overlay'}>
                      {saveError || saveMessage}
                    </div>
                  ) : null}
                  <Button onClick={handleSave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
                </div>
              </div>
            </>
          )}
        </div>
      </Card>

      {showLeaveModal ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" role="dialog" aria-modal="true" aria-labelledby="leave-modal-title">
            <h3 id="leave-modal-title" className="rz-modal-title">Wijzigingen niet opgeslagen</h3>
            <p className="rz-modal-text">Je hebt wijzigingen aangebracht die nog niet zijn opgeslagen.</p>
            <div className="rz-modal-actions">
              <Button variant="secondary" onClick={handleLeaveWithoutSaving}>Niet opslaan</Button>
              <Button onClick={handleSaveAndLeave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  )
}
