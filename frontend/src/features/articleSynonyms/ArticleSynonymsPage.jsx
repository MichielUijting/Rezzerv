import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import AppShell from '../../app/AppShell'
import ScreenCard from '../../ui/ScreenCard'
import DataTable from '../../ui/DataTable'
import Button from '../../ui/Button'
import CatalogProductImage from '../catalog/CatalogProductImage'
import { useAppFeedback } from '../../ui/AppFeedbackProvider'
import { fetchJsonWithAuth } from '../../lib/authSession'
import './synonymAnalysis.css'

const API = '/api/external-databases/article-synonyms'
const codeOf = (article) => article?.primary_gtin || article?.article_codes?.[0] || '—'
const order = { linked: 0, suggested: 1, other: 2 }
const orderedPair = (left, right) => [left, right].sort()

export default function ArticleSynonymsPage({ embedded = false }) {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [articles, setArticles] = useState([])
  const [activeArticle, setActiveArticle] = useState(searchParams.get('artikel') || '')
  const [options, setOptions] = useState([])
  const [checked, setChecked] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [loadingOptions, setLoadingOptions] = useState(false)
  const [saving, setSaving] = useState(false)
  const savingRef = useRef(false)
  const { showFeedback } = useAppFeedback()

  function reportError(message) {
    showFeedback({ variant: 'error', title: 'Artikel-synoniemen',
      message: String(message || 'Er is iets misgegaan.'), dismissMode: 'ok-only' })
  }

  function showConflict(first, count) {
    const type = first.conflict_type || 'unknown'
    const left = currentArticle?.name || 'Het gekozen artikel'
    const reason = first.conflict_detail || first.reason ||
      'De artikelidentiteit of GS1 GPC-classificatie komt niet overeen.'
    let remedy = 'Controleer de artikelgegevens voordat je opnieuw koppelt.'
    let action = ''
    if (type === 'gpc_mismatch') {
      remedy = 'Controleer de officiële GS1 GPC-indeling van beide artikelen. Is een indeling aantoonbaar onjuist, corrigeer die dan via GS1 GPC als je daarvoor bevoegd bent, of laat dit door een bevoegde gebruiker doen. Probeer daarna opnieuw.'
      action = 'Naar GS1 GPC'
    } else if (type === 'same_gtin' || type === 'shared_article_code') {
      remedy = 'De artikelen hebben een gedeelde productidentiteit. Bekijk de artikelgegevens in Catalogusdetail. Een al bestaande barcode kun je daar nog niet aanpassen; een feitelijk foutieve productidentiteit vraagt apart bevoegd beheer. Zijn het twee registraties van hetzelfde fysieke product, dan zijn dit geen afzonderlijke synoniemen.'
      action = 'Bekijk Catalogusdetail'
    }
    const extra = count > 1 ? ` Ook ${count - 1} andere geselecteerde artikel(en) hebben een blokkade. Er is niets gekoppeld.` : ' Er is niets gekoppeld.'
    const route = first.resolution_route
    showFeedback({
      variant: 'warning',
      title: 'Koppeling vraagt controle',
      message: `${left} ↔ ${first.name}`,
      detail: `${reason} ${remedy}${extra}`,
      dismissMode: 'ok-only',
      ...(route && action ? {
        primaryActionLabel: action,
        secondaryActionLabel: 'Sluiten',
        onPrimaryAction: () => navigate(route),
      } : {}),
      testId: 'article-synonyms-conflict',
    })
  }

  const loadArticles = useCallback(async (signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis`, { signal })
    if (!response.ok) throw new Error('Catalogusartikelen konden niet worden geladen.')
    const result = await response.json()
    if (!signal?.aborted) setArticles(result.items || [])
  }, [])

  const loadOptions = useCallback(async (id, signal) => {
    const response = await fetchJsonWithAuth(`${API}/analysis/${encodeURIComponent(id)}/options`, { signal })
    if (!response.ok) throw new Error('Synoniemrelaties konden niet worden geladen.')
    const result = await response.json()
    if (!signal?.aborted) setOptions(result.items || [])
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    loadArticles(controller.signal)
      .catch((err) => { if (!controller.signal.aborted) reportError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [loadArticles])

  useEffect(() => {
    const controller = new AbortController()
    setChecked(new Set())
    setOptions([])
    if (!activeArticle) return () => controller.abort()
    setLoadingOptions(true)
    loadOptions(activeArticle, controller.signal)
      .catch((err) => { if (!controller.signal.aborted) reportError(err.message) })
      .finally(() => { if (!controller.signal.aborted) setLoadingOptions(false) })
    return () => controller.abort()
  }, [activeArticle, loadOptions])

  function chooseArticle(id) {
    if (savingRef.current || loadingOptions) return
    setActiveArticle(id)
    setChecked(new Set())
  }

  function toggle(item) {
    if (savingRef.current || loadingOptions) return
    setChecked((previous) => {
      const next = new Set(previous)
      if (next.has(item.id)) next.delete(item.id)
      else {
        // Keep a single operation type: no mixed link/unlink selection.
        for (const id of next) {
          const previous = options.find((option) => option.id === id)
          if ((previous?.status === 'linked') !== (item.status === 'linked')) next.delete(id)
        }
        if (next.size < 200) next.add(item.id)
      }
      return next
    })
  }

  const currentArticle = articles.find((item) => item.id === activeArticle)
  const rightRows = [...options].sort((a, b) =>
    order[a.status] - order[b.status]
    || (b.score || 0) - (a.score || 0)
    || a.name.localeCompare(b.name, 'nl') || a.id.localeCompare(b.id)
  )
  const selectedLinks = options.filter((item) => checked.has(item.id) && item.status !== 'linked')
  const selectedUnlinks = options.filter((item) => checked.has(item.id) && item.status === 'linked')

  async function submitChange(action, selections, decisions = [], rethrow = false) {
    if (savingRef.current) return
    savingRef.current = true
    setSaving(true)
    try {
      const response = await fetchJsonWithAuth(`${API}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections, ...(decisions.length ? { decisions } : {}) }),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(
        typeof result.detail === 'string' ? result.detail : 'De synoniemrelaties konden niet worden bijgewerkt.'
      )
      await Promise.all([loadArticles(), loadOptions(activeArticle)])
      setChecked(new Set())
      const number = action === 'unlink' ? result.unlinked : result.linked
      const inheritance = action === 'link' ? result.classification_inheritance || {} : {}
      const conflicts = Array.isArray(inheritance.conflicts) ? inheritance.conflicts : []
      const gpcCount = Number(inheritance.gpc_inherited || 0)
      const cbsCount = Number(inheritance.cbs_inherited || 0)
      const gpcChosen = Number(inheritance.gpc_resolved || 0)
      const cbsChosen = Number(inheritance.cbs_resolved || 0)
      if (conflicts.length) {
        const systems = [...new Set(conflicts.map((conflict) => conflict.system))].join(', ')
        const route = conflicts.some((conflict) => conflict.system === 'GPC')
          ? '/catalogus/gpc-classificeren'
          : '/catalogus/artikelclassificaties-toekennen'
        showFeedback({
          variant: 'warning',
          title: 'Synoniemen gekoppeld; overige classificaties controleren',
          message: `${number} synoniemkoppeling(en) bevestigd.`,
          detail: `${gpcChosen} GS1 GPC- en ${cbsChosen} CBS-keuzes bevestigd. ${gpcCount} GS1 GPC en ${cbsCount} CBS overgenomen. Voor ${conflicts.length} overig(e) classificatieverschil(len) (${systems}) zijn bestaande waarden behouden.`,
          dismissMode: 'ok-only',
          primaryActionLabel: conflicts.some((conflict) => conflict.system === 'GPC') ? 'Naar GS1 GPC' : 'Naar CBS',
          secondaryActionLabel: 'Sluiten',
          onPrimaryAction: () => navigate(route),
          testId: 'article-synonyms-inheritance-conflict',
        })
      } else {
        showFeedback({
          variant: 'success',
          message: action === 'unlink'
            ? `${number} synoniemkoppeling(en) verwijderd.`
            : `${number} synoniemkoppeling(en) bevestigd. ${gpcCount} GS1 GPC en ${cbsCount} CBS automatisch overgenomen. ${gpcChosen} GS1 GPC- en ${cbsChosen} CBS-keuzes verwerkt.`,
        })
      }
    } catch (err) {
      if (rethrow) throw err
      reportError(err.message)
    } finally {
      savingRef.current = false
      setSaving(false)
    }
  }

  async function changeLinks(action) {
    if (savingRef.current || loadingOptions || !activeArticle) return
    const targets = action === 'unlink' ? selectedUnlinks : selectedLinks
    if (!targets.length) return
    if (action === 'link') {
      // Identical GTIN/retailer identities remain forbidden. GPC mismatch is
      // eligible ONLY for an explicit classified choice at confirmation.
      const identityBlocks = targets.filter((item) => !item.linkable && item.conflict_type !== 'gpc_mismatch')
      if (identityBlocks.length) {
        showConflict(identityBlocks[0], identityBlocks.length)
        return
      }
    }
    const selections = targets.map((item) => {
      const ids = orderedPair(activeArticle, item.id)
      return {
        left_product_id: ids[0],
        right_product_id: ids[1],
        fingerprint: item.fingerprint,
        ...(action === 'link' ? { manual: Boolean(item.manual) } : {}),
      }
    })
    if (selections.some((entry) => entry.left_product_id === entry.right_product_id)) {
      reportError('Een artikel kan niet aan zichzelf worden gekoppeld.')
      return
    }
    if (action === 'link') {
      let reviews = []
      savingRef.current = true
      setSaving(true)
      try {
        const response = await fetchJsonWithAuth(`${API}/link/review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ selections }),
        })
        const result = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(
          typeof result.detail === 'string' ? result.detail : 'Classificaties konden niet worden vergeleken.'
        )
        reviews = Array.isArray(result.items) ? result.items : []
      } catch (err) {
        reportError(err.message)
        return
      } finally {
        savingRef.current = false
        setSaving(false)
      }
      if (reviews.length) {
        const pairs = reviews.flatMap((review, i) =>
          review.clashes.map((clash) => ({ review, clash, fieldName: `choice_${i}_${clash.system}` }))
        )
        // Backend pair IDs are canonically ordered. Keep the visual comparison
        // aligned with the actually selected left and right table articles.
        const orientedPairs = pairs.map(({ clash, fieldName }) => ({
          clash,
          fieldName,
          left: clash.left.id === activeArticle ? clash.left : clash.right,
          right: clash.left.id === activeArticle ? clash.right : clash.left,
        }))
        const comparisonRows = orientedPairs.map(({ clash, left, right }) => ({
          system: clash.system === 'GPC' ? 'GS1 GPC — producttype' : 'CBS ECOICOPv2 — bestedingsdoel',
          leftName: left.name,
          rightName: right.name,
          leftValue: `${left.code}${left.reference ? ' (' + left.reference + ')' : ''} — ${left.label}`,
          rightValue: `${right.code}${right.reference ? ' (' + right.reference + ')' : ''} — ${right.label}`,
        }))
        const inputFields = orientedPairs.map(({ clash, fieldName, left, right }) => ({
          name: fieldName,
          label: `${clash.system === 'GPC' ? 'GS1 GPC' : 'CBS'}: welke classificatie moet gelden voor beide artikelen?`,
          type: 'select',
          required: true,
          options: [
            { value: left.id, label: `${left.name}: ${left.code} — ${left.label}` },
            { value: right.id, label: `${right.name}: ${right.code} — ${right.label}` },
          ],
        }))
        showFeedback({
          variant: 'warning',
          title: 'Kies welke artikelclassificatie moet gelden',
          message: 'De geselecteerde artikelen hebben verschillende bevestigde classificaties.',
          detail: 'Bekijk de beide bestaande indelingen. Kies per classificatiesysteem welke moet prevaleren. Daarmee wordt de andere officiële indeling bewust vervangen. Zonder bevestiging wordt niets gekoppeld of gewijzigd.',
          comparisonRows,
          inputFields,
          primaryActionLabel: 'Keuze bevestigen en koppelen',
          secondaryActionLabel: 'Annuleren',
          dismissMode: 'ok-only',
          testId: 'article-synonyms-classification-choice',
          onPrimaryAction: async (values) => {
            const decisions = reviews.map((review, i) => ({
              left_product_id: review.left_id,
              right_product_id: review.right_id,
              snapshot: review.snapshot,
              ...Object.fromEntries(review.clashes.map((clash) => [
                clash.system === 'GPC' ? 'gpc_source_id' : 'cbs_source_id',
                values[`choice_${i}_${clash.system}`],
              ])),
            }))
            await submitChange('link', selections, decisions, true)
            // submitChange presents the actual outcome via standard feedback.
            return false
          },
        })
        return
      }
    }
    await submitChange(action, selections)
  }

  const leftColumns = [
    { key: 'selected', label: '', width: 42 },
    { key: 'photo', label: 'Foto', width: 70 },
    { key: 'name', label: 'Artikelnaam', width: 236, sortable: true, filterable: true },
    { key: 'code', label: 'Barcode', width: 112, sortable: true, filterable: true },
    { key: 'synonym_count', label: 'Syn.', width: 52, sortable: true, align: 'right' },
  ]
  const rightColumns = [
    { key: 'selected', label: '', width: 42 },
    { key: 'photo', label: 'Foto', width: 70 },
    { key: 'name', label: 'Artikelnaam', width: 250, sortable: true, filterable: true },
    { key: 'code', label: 'Barcode', width: 150, sortable: true, filterable: true },
  ]
  const content = <>
    <ScreenCard fullWidth>
      <h2>Artikel-synoniemen</h2>
      <div className="rz-synonym-side-by-side">
        <section className="rz-synonym-side" aria-label="Catalogusartikelen links">
          <h3>Artikel kiezen</h3>
          <DataTable columns={leftColumns}
            data={articles.map((item) => ({ ...item, code: codeOf(item) }))}
            getRowKey={(item) => item.id} pageSize={10}
            wrapperClassName="rz-synonym-analysis-table-wrapper"
            dataTestId="article-synonyms-articles"
            paginationActions={<span className="rz-synonym-pagination-spacer" aria-hidden="true" />}
            emptyMessage={loading ? 'Catalogusartikelen laden...' : 'Geen gecodeerde Catalogusartikelen.'}
            renderRow={(item) => <tr key={item.id}
              className="rz-synonym-analysis-main-row"
              tabIndex={0} aria-selected={activeArticle === item.id}
              aria-label={`Artikel kiezen: ${item.name}, barcode ${item.code}`}
              onClick={() => chooseArticle(item.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  chooseArticle(item.id)
                }
              }}>
              <td><input type="checkbox" checked={activeArticle === item.id}
                aria-label={`Selecteer links ${item.name}, barcode ${item.code}`}
                disabled={saving || loadingOptions}
                onClick={(event) => event.stopPropagation()}
                onChange={() => chooseArticle(activeArticle === item.id ? '' : item.id)} /></td>
              <td><CatalogProductImage imageUrl={item.image_url} productName={item.name} compact /></td>
              <td>{item.name}</td>
              <td>{item.code}</td>
              <td className="rz-num">{Number(item.synonym_count) || 0}</td>
            </tr>} />
          <div className="rz-synonym-actions-placeholder" aria-hidden="true" />
        </section>
        <section className="rz-synonym-side" aria-label="Synoniemen rechts"
          data-testid="article-synonyms-candidates">
          <h3>Te koppelen artikelen</h3>
          <DataTable columns={rightColumns}
            data={currentArticle ? rightRows.map((item) => ({ ...item, code: codeOf(item) })) : []}
            getRowKey={(item) => item.id} pageSize={10}
            wrapperClassName="rz-synonym-analysis-table-wrapper"
            dataTestId="article-synonyms-table"
            paginationActions={<span className="rz-synonym-pagination-spacer" aria-hidden="true" />}
            emptyMessage={!currentArticle
              ? 'Selecteer links één artikel.'
              : loadingOptions ? 'Artikelen laden...' : 'Geen andere gecodeerde artikelen.'}
            renderRow={(item) => <tr key={item.id}
              tabIndex={0}
              className={`rz-synonym-analysis-candidate-row rz-synonym-relation-${item.status}`}
              aria-selected={checked.has(item.id)}
              aria-label={`${item.status_label}: ${item.name}, barcode ${item.code}`}
              title={item.reason ? `${item.status_label}: ${item.reason}` : item.status_label}
              onClick={() => toggle(item)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  toggle(item)
                }
              }}>
              <td><input type="checkbox"
                checked={checked.has(item.id)}
                disabled={saving || loadingOptions}
                aria-label={`Selecteer rechts ${item.name}, barcode ${item.code} (${item.status_label})`}
                onClick={(event) => event.stopPropagation()}
                onChange={() => toggle(item)} /></td>
              <td><CatalogProductImage imageUrl={item.image_url} productName={item.name} compact /></td>
              <td>{item.name}</td>
              <td>{item.code}</td>
            </tr>}
          />
          <div className="rz-synonym-analysis-actions">
            <Button disabled={loading || loadingOptions || saving || !selectedLinks.length}
              onClick={() => changeLinks('link')}>Koppelen</Button>
            <Button disabled={loading || loadingOptions || saving || !selectedUnlinks.length}
              onClick={() => changeLinks('unlink')}>Ontkoppelen</Button>
          </div>
        </section>
      </div>
    </ScreenCard>
  </>
  return embedded ? content : <AppShell title="Artikel-synoniemen" showExit={false}>{content}</AppShell>
}
