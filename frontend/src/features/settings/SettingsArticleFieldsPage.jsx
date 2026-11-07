import { useEffect, useMemo, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import Card from '../../ui/Card'
import Button from '../../ui/Button'
import { useArticleFieldVisibility } from '../articles/hooks/useArticleFieldVisibility'
import { ARTICLE_TABS } from '../articles/config/articleFieldConstants'
import { getFieldsByTabAndGroup } from '../articles/config/articleFieldHelpers'
import FieldVisibilitySection from './components/FieldVisibilitySection'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'

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
  const { showFeedback } = useAppFeedback()
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState('')
  const [showLeaveModal, setShowLeaveModal] = useState(false)
  const groupedFieldsByTab = useMemo(() => ({
    [ARTICLE_TABS.OVERVIEW]: getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW),
    [ARTICLE_TABS.STOCK]: {},
    [ARTICLE_TABS.LOCATIONS]: {},
    [ARTICLE_TABS.HISTORY]: {},
    [ARTICLE_TABS.ANALYTICS]: {},
  }), [])

  const currentSnapshot = useMemo(() => stableStringify(visibilityMap || {}), [visibilityMap])
  const isDirty = !isLoading && !!lastSavedSnapshot && currentSnapshot !== lastSavedSnapshot
  const blocker = useBlocker(isDirty)

  useEffect(() => {
    if (error) showFeedback({ variant: 'error', message: 'De standaardweergave is geladen omdat voorkeuren niet konden worden opgehaald.' })
  }, [error, showFeedback])

  useEffect(() => {
    if (!isLoading && !lastSavedSnapshot) {
      setLastSavedSnapshot(currentSnapshot)
    }
  }, [isLoading, lastSavedSnapshot, currentSnapshot])

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

  async function handleSave() {
    const result = await saveVisibility()

    if (result.ok) {
      const savedSnapshot = stableStringify(result.data || visibilityMap || {})
      setLastSavedSnapshot(savedSnapshot)
      return true
    }

    showFeedback({ variant: 'error', message: result.error?.message || 'Opslaan is niet gelukt.' })
    return false
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

  function handleResetDefaults() {
    resetToDefault()
  }

  function handleShowAll() {
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
              <FieldVisibilitySection title={TAB_LABELS.overview} tabKey={ARTICLE_TABS.OVERVIEW} groupedFields={groupedFieldsByTab[ARTICLE_TABS.OVERVIEW]} visibilityMap={visibilityMap} alwaysVisibleKeys={alwaysVisibleKeys} onToggle={toggleFieldVisibility} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <Button variant="secondary" onClick={handleResetDefaults} disabled={isSaving}>Herstel standaardweergave</Button>
                  <Button variant="secondary" onClick={handleShowAll} disabled={isSaving}>Alles tonen</Button>
                </div>
                <div className="rz-save-cluster">
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
