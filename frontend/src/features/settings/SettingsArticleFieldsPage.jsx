import { useMemo, useState } from 'react'
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

export default function SettingsArticleFieldsPage() {
  const { visibilityMap, alwaysVisibleKeys, isLoading, isSaving, error, toggleFieldVisibility, resetToDefault, showAllFields, saveVisibility } = useArticleFieldVisibility()
  const [message, setMessage] = useState('')

  const groupedFieldsByTab = useMemo(() => ({
    [ARTICLE_TABS.OVERVIEW]: getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW),
    [ARTICLE_TABS.STOCK]: getFieldsByTabAndGroup(ARTICLE_TABS.STOCK),
    [ARTICLE_TABS.LOCATIONS]: {},
    [ARTICLE_TABS.HISTORY]: {},
    [ARTICLE_TABS.ANALYTICS]: {},
  }), [])

  async function handleSave() {
    const result = await saveVisibility()
    setMessage(result.ok ? 'Instellingen opgeslagen.' : 'Opslaan is niet gelukt.')
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
              {error ? <div style={{ color: '#9c4221' }}>De standaardweergave is geladen omdat voorkeuren niet konden worden opgehaald.</div> : null}
              <FieldVisibilitySection title={TAB_LABELS.overview} tabKey={ARTICLE_TABS.OVERVIEW} groupedFields={groupedFieldsByTab[ARTICLE_TABS.OVERVIEW]} visibilityMap={visibilityMap} alwaysVisibleKeys={alwaysVisibleKeys} onToggle={toggleFieldVisibility} />
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                  <Button variant="secondary" onClick={() => { setMessage(''); resetToDefault() }} disabled={isSaving}>Herstel standaardweergave</Button>
                  <Button variant="secondary" onClick={() => { setMessage(''); showAllFields() }} disabled={isSaving}>Alles tonen</Button>
                </div>
                <Button onClick={handleSave} disabled={isSaving}>{isSaving ? 'Opslaan…' : 'Opslaan'}</Button>
              </div>
              {message ? <div style={{ color: '#2e7d4d' }}>{message}</div> : null}
            </>
          )}
        </div>
      </Card>
    </AppShell>
  )
}
