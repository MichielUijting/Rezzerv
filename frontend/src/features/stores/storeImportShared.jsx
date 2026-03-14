import { useEffect, useMemo, useState } from 'react'
import Button from '../../ui/Button'
import demoData from '../../demo-articles.json'

export function normalizeErrorMessage(value) {
  if (!value) return 'Verzoek mislukt'
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    const first = value[0]
    if (typeof first === 'string') return first
    if (first && typeof first === 'object') {
      const message = first.msg || first.message || null
      if (message) return message
    }
    return 'Verzoek mislukt'
  }
  if (typeof value === 'object') {
    return value.detail || value.message || value.msg || 'Verzoek mislukt'
  }
  return 'Verzoek mislukt'
}

export async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    cache: options.cache || 'no-store',
    ...options,
  })

  const responseText = await response.text()
  const contentType = (response.headers.get('content-type') || '').toLowerCase()
  const looksLikeJson = contentType.includes('application/json') || /^\s*[\[{]/.test(responseText)

  let data = null
  if (responseText) {
    if (looksLikeJson) {
      try {
        data = JSON.parse(responseText)
      } catch (error) {
        if (!response.ok) {
          throw new Error('Winkelgegevens konden niet volledig worden geladen')
        }
        throw new Error('De server gaf ongeldige gegevens terug')
      }
    } else if (!response.ok) {
      throw new Error(normalizeErrorMessage(responseText) || 'Winkelgegevens konden niet volledig worden geladen')
    }
  }

  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data?.detail || data || responseText))
  }

  return data
}

export const articleFallbackOptions = demoData.articles.map((article) => ({
  id: String(article.id),
  name: article.name,
  brand: article.brand || '',
}))

export function articleLabel(article) {
  return article.brand ? `${article.name} — ${article.brand}` : article.name
}

export function StoreArticleSelector({
  lineId,
  lineName,
  selectedArticleId,
  articleOptions,
  disabled,
  onChange,
  onClearArticle,
  onCreateArticle,
}) {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [newArticleName, setNewArticleName] = useState('')
  const [createArticleError, setCreateArticleError] = useState('')

  const canCreateArticle = typeof onCreateArticle === 'function'

  function openCreateArticleModal() {
    const baseName = lineName || ''
    setNewArticleName(baseName)
    setCreateArticleError('')
    setIsCreateModalOpen(true)
  }

  function closeCreateArticleModal() {
    setIsCreateModalOpen(false)
    setCreateArticleError('')
  }

  async function handleCreateArticle() {
    const nextName = newArticleName.trim() || lineName || ''
    if (!nextName) {
      setCreateArticleError('Vul eerst een artikelnaam in.')
      return
    }
    const created = await onCreateArticle(nextName)
    if (created?.id) {
      onChange(String(created.id))
      closeCreateArticleModal()
      return
    }
    setCreateArticleError('Het artikel kon niet worden aangemaakt.')
  }

  function handleSelectChange(event) {
    const nextId = String(event.target.value || '')
    if (!nextId) {
      onClearArticle?.()
      return
    }
    onChange(nextId)
  }

  return (
    <div className="rz-store-article-search" style={articleSearchStyle}>
      <select
        className="rz-input rz-store-select"
        data-store-article-select="true"
        value={selectedArticleId || ''}
        disabled={disabled}
        onChange={handleSelectChange}
      >
        <option value="">Kies artikel</option>
        {articleOptions.map((article) => (
          <option key={article.id} value={article.id}>{articleLabel(article)}</option>
        ))}
      </select>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        {canCreateArticle ? (
          <button
            type="button"
            className="rz-link-button"
            data-testid={`store-create-article-trigger-${lineId}`}
            style={createArticleButtonStyle}
            disabled={disabled}
            onClick={openCreateArticleModal}
          >
            Nieuw artikel aanmaken
          </button>
        ) : null}
      </div>
      {isCreateModalOpen ? (
        <div className="rz-modal-backdrop" role="presentation">
          <div className="rz-modal-card" data-testid={`store-create-article-modal-${lineId}`} role="dialog" aria-modal="true" aria-labelledby={`store-create-article-title-${lineId}`}>
            <h3 id={`store-create-article-title-${lineId}`} className="rz-modal-title">Nieuw artikel aanmaken</h3>
            <p className="rz-modal-text">Maak een nieuw Rezzerv-artikel aan voor deze winkelregel.</p>
            <div className="rz-store-modal-field">
              <label className="rz-store-modal-label" htmlFor={`store-create-article-input-${lineId}`}>Artikelnaam</label>
              <input
                id={`store-create-article-input-${lineId}`}
                className="rz-input"
                data-testid={`store-create-article-input-${lineId}`}
                type="text"
                value={newArticleName}
                disabled={disabled}
                onChange={(event) => {
                  setNewArticleName(event.target.value)
                  if (createArticleError) setCreateArticleError('')
                }}
              />
            </div>
            {createArticleError ? <div className="rz-inline-feedback rz-store-modal-feedback">{createArticleError}</div> : null}
            <div className="rz-modal-actions">
              <Button variant="secondary" data-testid={`store-create-article-cancel-${lineId}`} type="button" onClick={closeCreateArticleModal} disabled={disabled}>Terug</Button>
              <Button variant="primary" type="button" onClick={handleCreateArticle} disabled={disabled}>Opslaan</Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function providerLabel(providerOrConnection) {
  return providerOrConnection?.store_provider_name || providerOrConnection?.name || providerOrConnection?.store_provider_code || providerOrConnection?.code || 'Winkel'
}

export function providerStatusLabel(provider) {
  if (!provider) return 'niet beschikbaar'
  return `${provider.status} / ${provider.import_mode}`
}

export function buildBatchTitle(batch) {
  const providerName = batch?.store_provider_name || batch?.store_name || 'Winkel'
  return `Kassabon ${providerName}`
}

export function batchStatusLabel(value) {
  if (value === 'processed') return 'Verwerkt naar voorraad'
  if (value === 'partially_processed') return 'Gedeeltelijk verwerkt'
  if (value === 'failed') return 'Verwerking mislukt'
  if (value === 'reviewed') return 'Beoordeling afgerond'
  if (value === 'in_review') return 'In bewerking'
  return 'Nog te beoordelen'
}

export function suggestionLabel(line) {
  if (line?.preparation_explanation) return line.preparation_explanation
  if (line?.suggestion_reason) return line.suggestion_reason
  if (line?.is_auto_prefilled && (line.review_decision || 'pending') === 'selected' && line.matched_household_article_id && line.target_location_id) {
    return 'Automatisch voorbereid'
  }
  if (line?.suggested_household_article_id || line?.suggested_location_id) {
    return 'Controleer voorstel'
  }
  return 'Geen eerdere mapping gevonden'
}

export function formatQuantity(value, unit) {
  return [value, unit].filter(Boolean).join(' ')
}

export function deriveBatchUiState(batch) {
  const lines = Array.isArray(batch?.lines) ? batch.lines : []
  const summary = batch?.summary || {}
  const totalLines = Number(summary.total || lines.length || 0)
  const processedCount = Number(summary.processed || lines.filter((line) => (line.processing_status || 'pending') === 'processed').length || 0)
  const failedCount = Number(summary.failed || lines.filter((line) => (line.processing_status || 'pending') === 'failed').length || 0)
  const visibleLines = lines.filter((line) => (line.processing_status || 'pending') !== 'processed')
  const selectedLines = visibleLines.filter((line) => (line.review_decision || 'pending') === 'selected')
  const readyLines = selectedLines.filter((line) => line.matched_household_article_id && line.target_location_id)
  const blockedLines = selectedLines.length - readyLines.length
  const pendingReviewCount = visibleLines.filter((line) => (line.review_decision || 'pending') === 'pending').length
  const openCount = Math.max(visibleLines.length - readyLines.length, 0)
  const isProcessed = (batch?.import_status || '') === 'processed'
  const canResume = !isProcessed
  const countsReason = `${readyLines.length} klaar · ${openCount} open · ${blockedLines} geblokkeerd · ${processedCount} verwerkt`

  if (isProcessed) {
    return {
      statusKey: 'processed',
      label: 'Verwerkt',
      actionLabel: 'Openen',
      actionType: 'open',
      rank: 99,
      progressText: totalLines > 0 ? `${processedCount} verwerkt` : 'Afgerond',
      statusReason: failedCount > 0
        ? `Batch is afgerond met ${processedCount} verwerkte en ${failedCount} mislukte regel(s).`
        : `Batch is afgerond. ${processedCount} regel(s) zijn verwerkt.`,
      primaryActionReason: 'De batch is al afgerond; je kunt de resultaten openen.',
      canResume,
      countsReason,
    }
  }

  if (blockedLines > 0) {
    return {
      statusKey: 'action_needed',
      label: 'Actie nodig',
      actionLabel: 'Hervatten',
      actionType: 'resume',
      rank: 0,
      progressText: `${readyLines.length} klaar / ${blockedLines} geblokkeerd`,
      statusReason: `${blockedLines} regel(s) missen nog een artikel of locatie en vragen gebruikersactie.`,
      primaryActionReason: 'Kies Hervatten om de openstaande of geblokkeerde regels in de bon af te maken.',
      canResume,
      countsReason,
    }
  }

  if (selectedLines.length > 0 && pendingReviewCount === 0) {
    return {
      statusKey: 'ready',
      label: 'Klaar voor verwerking',
      actionLabel: 'Naar voorraad',
      actionType: 'process',
      rank: 1,
      progressText: `${readyLines.length} klaar om te verwerken`,
      statusReason: `${readyLines.length} regel(s) zijn volledig voorbereid en kunnen nu naar de voorraad worden verwerkt.`,
      primaryActionReason: 'De primaire actie is Naar voorraad omdat alle geselecteerde regels klaarstaan. De bon blijft wel hervatbaar zolang de batch niet is afgerond.',
      canResume,
      countsReason,
    }
  }

  if ((batch?.import_status || '') === 'in_review' || (batch?.import_status || '') === 'reviewed' || selectedLines.length > 0 || pendingReviewCount < visibleLines.length) {
    return {
      statusKey: 'in_progress',
      label: 'In bewerking',
      actionLabel: 'Hervatten',
      actionType: 'resume',
      rank: 2,
      progressText: visibleLines.length > 0 ? `${readyLines.length} klaar / ${openCount} open` : 'Beoordeling loopt',
      statusReason: visibleLines.length > 0
        ? `De bon is nog niet afgerond. ${countsReason}.`
        : 'De bon wordt nog beoordeeld of opnieuw geladen.',
      primaryActionReason: 'Kies Hervatten om de bon verder te beoordelen voordat deze naar voorraad gaat.',
      canResume,
      countsReason,
    }
  }

  return {
    statusKey: 'open',
    label: 'Open',
    actionLabel: 'Openen',
    actionType: 'open',
    rank: 3,
    progressText: totalLines > 0 ? `${totalLines} regel(s) wachten op beoordeling` : 'Nog te beoordelen',
    statusReason: totalLines > 0
      ? `${totalLines} regel(s) wachten nog op beoordeling of koppeling.`
      : 'Nog te beoordelen.',
    primaryActionReason: 'Kies Openen om de bon te starten of verder te beoordelen.',
    canResume,
    countsReason,
  }
}

export function formatBatchLastChange(batch) {
  const rawValue = batch?.created_at || ''
  if (!rawValue) return 'Onbekend'
  const date = new Date(rawValue)
  if (Number.isNaN(date.getTime())) return rawValue
  return new Intl.DateTimeFormat('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export const batchStatusToneStyles = {
  action_needed: { color: '#b42318', background: '#fef3f2' },
  ready: { color: '#175cd3', background: '#eff8ff' },
  in_progress: { color: '#b54708', background: '#fffaeb' },
  open: { color: '#1d2939', background: '#f2f4f7' },
  processed: { color: '#027a48', background: '#ecfdf3' },
}

export const batchStatusPillStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '6px 12px',
  borderRadius: '999px',
  fontSize: '13px',
  fontWeight: 700,
}

export const connectedStoreRowStyle = {
  display: 'grid',
  gridTemplateColumns: '1fr auto',
  gap: '12px',
  alignItems: 'center',
  padding: '12px 0',
  borderTop: '1px solid #eaecf0',
}

const articleSearchStyle = {
  display: 'grid',
  gap: '8px',
}

const articleSearchInputStyle = {
  width: '100%',
}

const createArticleButtonStyle = {
  justifySelf: 'start',
  padding: 0,
  border: 'none',
  background: 'none',
  color: '#175cd3',
  fontWeight: 600,
  cursor: 'pointer',
}
