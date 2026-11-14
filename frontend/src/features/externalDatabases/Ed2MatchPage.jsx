import { useCallback, useEffect, useMemo, useState } from 'react'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../lib/authSession'
import { useAppFeedback } from '../../ui/AppFeedbackProvider.jsx'
import Ed2CuratedMatchingBatch from './Ed2CuratedMatchingBatch'
import Ed2CourgetteFamilyPanel from './Ed2CourgetteFamilyPanel'
import '../articleSynonyms/synonymAnalysis.css'

const RETAILERS = {
  ah: 'Albert Heijn', albert_heijn: 'Albert Heijn', jumbo: 'Jumbo',
  lidl: 'Lidl', aldi: 'Aldi', plus: 'PLUS', picnic: 'Picnic',
}
const columns = [
  { key: 'selected', label: '', width: 44 },
  { key: 'receipt_line_text', label: 'Artikel', width: 210, sortable: true, filterable: true },
  { key: 'retailer', label: 'Winkelketen', width: 108, sortable: true, filterable: true },
  { key: 'receipt_article_number', label: 'Bonartikelnummer', width: 126, sortable: true, filterable: true },
  { key: 'barcode', label: 'Art./Barcode', width: 145, sortable: true, filterable: true },
]

function curatedCourgette(value) {
  const words = String(value || '').toLocaleLowerCase('nl')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .match(/[a-z0-9]+/g) || []
  const base = new Set(['courgette', 'courgettes'])
  const allowed = new Set([...base, 'bio', 'biologisch', 'biologische',
    'groen', 'groene', 'geel', 'gele', 'ah', 'jumbo', 'lidl', 'albert', 'heijn'])
  const colors = [words.some((w) => w === 'groen' || w === 'groene'),
    words.some((w) => w === 'geel' || w === 'gele')]
  return words.filter((w) => base.has(w)).length === 1
    && words.every((w) => allowed.has(w)) && !colors.every(Boolean)
}

function displayRow(item) {
  return { ...item, retailer: RETAILERS[item.retailer_code] || item.retailer_code || 'Onbekend',
    barcode: item.article_code || item.manual_barcode || '' }
}

function confirmedTarget(item) {
  if (item.identity_status !== 'catalog_linked') return false
  const explicit = String(item.identity_catalog_product_id || '')
  const central = String(item.catalog_product_id || '')
  return Boolean(explicit || central) && !(explicit && central && explicit !== central)
    && Boolean(String(item.receipt_article_number || '') || item.article_code)
    && !(item.article_code && item.manual_barcode && item.article_code !== item.manual_barcode)
}

export default function Ed2MatchPage() {
  const { showFeedback } = useAppFeedback()
  const isSuperuser = Boolean(readStoredAuthContext()?.is_platform_superuser)
  const [items, setItems] = useState([])
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const response = await fetchJsonWithAuth('/api/external-databases/articles-overview')
      if (!response.ok) throw new Error('Bonartikelen konden niet worden opgehaald.')
      const payload = await response.json()
      setItems((payload.items || []).map(displayRow))
    } catch (error) {
      showFeedback({ variant: 'error', title: 'Matchen',
        message: error.message || 'De bonartikelen konden niet worden geladen.' })
    } finally { setLoading(false) }
  }, [showFeedback])

  useEffect(() => { if (isSuperuser) reload() }, [isSuperuser, reload])

  const leftRows = useMemo(() => items.filter((item) =>
    item.identity_status === 'not_identified'
      || (!item.identity_status && !item.catalog_product_id && !item.article_code)), [items])
  const rightRows = useMemo(() => items.filter(confirmedTarget), [items])
  const left = leftRows.find((item) => item.id === leftId)
  const right = rightRows.find((item) => item.id === rightId)

  function matchSelected() {
    if (!left || !right || saving || loading) return
    showFeedback({
      variant: 'warning', title: 'Bonartikelen matchen?',
      message: left.receipt_line_text + ' (' + left.retailer + ') koppelen aan hetzelfde Catalogusproduct als '
        + right.receipt_line_text + ' (' + right.retailer + ')?',
      detail: 'Inhuis controleert beide bonartikelidentiteiten opnieuw. Er wordt geen barcode overgenomen, geen Catalogusproduct aangemaakt en geen voorraad gewijzigd. Alleen deze specifieke bonartikelcombinatie wordt gekoppeld.',
      primaryActionLabel: 'Match bevestigen', secondaryActionLabel: 'Annuleren',
      testId: 'ed2-manual-match-confirm',
      onPrimaryAction: async () => {
        setSaving(true)
        try {
          const response = await fetchJsonWithAuth('/api/catalog/ed2/manual-receipt-match/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              source_receipt_item_id: left.id, target_receipt_item_id: right.id,
            }),
          })
          const payload = await response.json().catch(() => ({}))
          if (!response.ok || payload.ok !== true) {
            throw new Error(typeof payload.detail === 'string' ? payload.detail
              : 'De match is niet bevestigd.')
          }
          setLeftId('')
          setRightId('')
          await reload()
          showFeedback({ variant: 'success', title: 'Bonartikel gematcht',
            message: 'De bestaande Catalogusidentiteit is gekoppeld. Er is geen barcode overgenomen.' })
        } catch (error) {
          showFeedback({ variant: 'error', title: 'Matching niet verwerkt',
            message: error.message || 'Controleer de actuele gegevens.' })
        } finally { setSaving(false) }
        return false
      },
    })
  }

  function selectCell(item, selectedId, setSelectedId) {
    if (saving || loading) return
    setSelectedId(item.id === selectedId ? '' : item.id)
  }

  function articleTable(rows, chosen, setChosen, side) {
    return <DataTable columns={columns} data={rows} getRowKey={(item) => item.id}
      pageSize={10} wrapperClassName="rz-synonym-analysis-table-wrapper"
      dataTestId={'ed2-match-' + side + '-table'}
      paginationActions={<span className="rz-synonym-pagination-spacer" aria-hidden="true" />}
      emptyMessage={loading ? 'Artikelen laden...' : side === 'left'
        ? 'Geen nog te identificeren bonartikelen.' : 'Geen bewezen Catalogusartikelen beschikbaar.'}
      renderRow={(item) => <tr key={item.id} tabIndex={0}
        className="rz-synonym-analysis-main-row" aria-selected={chosen === item.id}
        onClick={() => selectCell(item, chosen, setChosen)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            selectCell(item, chosen, setChosen)
          }
        }}>
        <td><input type="checkbox" checked={chosen === item.id}
          disabled={saving || loading}
          aria-label={(side === 'left' ? 'Selecteer links ' : 'Selecteer rechts ')
            + item.receipt_line_text + ', ' + item.retailer
            + ', bonartikelnummer ' + (item.receipt_article_number || 'ontbreekt')}
          onClick={(event) => event.stopPropagation()}
          onChange={() => selectCell(item, chosen, setChosen)} /></td>
        <td>{item.receipt_line_text}
          {item.automatic_match_review_reason ? <span className="rz-synonym-review-hint"
            title={item.automatic_match_review_reason}>{item.automatic_match_review_reason}</span> : null}</td>
        <td>{item.retailer}</td>
        <td>{item.receipt_article_number || '—'}</td>
        <td>{item.barcode || '—'}</td>
      </tr>} />
  }

  if (!isSuperuser) return <p>Matchen is uitsluitend beschikbaar voor de Superuser.</p>

  return <section aria-label="Bonartikelen matchen" data-testid="ed2-match-workspace">
    <h2>Matchen</h2>
    <p>Kies links een nog te identificeren bonartikel en rechts een al bevestigd bonartikel.
      Beide tabellen hebben dezelfde kolommen, filters en paginering.
      De koppeling gebruikt het bewezen Catalogusproduct van de rechterregel.</p>
    <div className="rz-synonym-side-by-side">
      <section className="rz-synonym-side" aria-label="Bonartikelen links">
        <div className="rz-synonym-side-heading"><h3>Artikel kiezen</h3>
          <span>{leftRows.length} te beoordelen</span></div>
        {articleTable(leftRows, leftId, setLeftId, 'left')}
        <div className="rz-synonym-actions-placeholder" aria-hidden="true" />
      </section>
      <section className="rz-synonym-side" aria-label="Bonartikelen rechts">
        <div className="rz-synonym-side-heading"><h3>Te koppelen artikelen</h3>
          <span>{rightRows.length} bewezen</span></div>
        {articleTable(rightRows, rightId, setRightId, 'right')}
        <div className="rz-synonym-analysis-actions">
          <Button disabled={!left || !right || saving || loading} onClick={matchSelected}>
            {saving ? 'Matchen...' : 'Bonartikel matchen'}
          </Button>
        </div>
      </section>
    </div>
    {left && !left.article_code && !left.manual_barcode && curatedCourgette(left.receipt_line_text)
      ? <Ed2CourgetteFamilyPanel item={left} onConfirmed={() => {
        setLeftId('')
        setRightId('')
        reload()
      }} /> : null}
    <details className="rz-match-tools">
      <summary>Automatisch matchen en bonnaamregels</summary>
      <Ed2CuratedMatchingBatch onConfirmed={() => {
        setLeftId('')
        setRightId('')
        reload()
      }} />
    </details>
  </section>
}
