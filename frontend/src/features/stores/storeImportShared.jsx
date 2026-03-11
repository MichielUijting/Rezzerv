import { useEffect, useMemo, useState } from 'react'
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
  onCreateArticle,
}) {
  const datalistId = `store-article-options-${lineId}`
  const optionsByLabel = useMemo(() => {
    const entries = articleOptions.map((article) => [articleLabel(article), String(article.id)])
    return new Map(entries)
  }, [articleOptions])
  const labelById = useMemo(() => {
    const entries = articleOptions.map((article) => [String(article.id), articleLabel(article)])
    return new Map(entries)
  }, [articleOptions])
  const [query, setQuery] = useState(selectedArticleId ? (labelById.get(String(selectedArticleId)) || '') : '')

  useEffect(() => {
    const nextValue = selectedArticleId ? (labelById.get(String(selectedArticleId)) || '') : ''
    setQuery(nextValue)
  }, [selectedArticleId, labelById])

  const normalizedQuery = query.trim().toLowerCase()
  const hasExactMatch = Boolean(normalizedQuery && Array.from(optionsByLabel.keys()).some((label) => label.trim().toLowerCase() === normalizedQuery))
  const canCreateArticle = Boolean(normalizedQuery) && !hasExactMatch && !selectedArticleId

  async function handleCreateArticle() {
    const baseName = query.trim() || lineName || ''
    const nextName = window.prompt('Nieuw artikel aanmaken', baseName)
    if (!nextName) return
    const created = await onCreateArticle(nextName)
    if (created?.name) {
      setQuery(articleLabel(created))
    }
  }

  function handleInputChange(event) {
    const nextQuery = event.target.value
    setQuery(nextQuery)
    if (!nextQuery) {
      onChange('')
      return
    }
    const matchedId = optionsByLabel.get(nextQuery)
    if (matchedId) {
      onChange(matchedId)
    }
  }

  function handleSelectChange(event) {
    const nextId = String(event.target.value || '')
    const nextLabel = nextId ? (labelById.get(nextId) || '') : ''
    setQuery(nextLabel)
    onChange(nextId)
  }

  return (
    <div className="rz-store-article-search" style={articleSearchStyle}>
      <input
        className="rz-input rz-store-article-search-input" style={articleSearchInputStyle}
        type="text"
        list={datalistId}
        value={query}
        placeholder="Kies artikel"
        disabled={disabled}
        onChange={handleInputChange}
      />
      <datalist id={datalistId}>
        {articleOptions.map((article) => (
          <option key={article.id} value={articleLabel(article)} />
        ))}
      </datalist>
      <select
        className="rz-input rz-store-select rz-store-select--hidden"
        style={{ display: 'none' }}
        data-store-article-select="true"
        value={selectedArticleId || ''}
        disabled={disabled}
        onChange={handleSelectChange}
        aria-hidden="true"
        tabIndex={-1}
      >
        <option value="">Kies artikel</option>
        {articleOptions.map((article) => (
          <option key={article.id} value={article.id}>{articleLabel(article)}</option>
        ))}
      </select>
      {canCreateArticle ? (
        <button
          type="button"
          className="rz-link-button"
          style={createArticleButtonStyle}
          disabled={disabled}
          onClick={handleCreateArticle}
        >
          Nieuw artikel aanmaken
        </button>
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
  const visibleLines = lines.filter((line) => (line.processing_status || 'pending') !== 'processed')
  const selectedLines = visibleLines.filter((line) => (line.review_decision || 'pending') === 'selected')
  const readyLines = selectedLines.filter((line) => line.matched_household_article_id && line.target_location_id)
  const blockedLines = selectedLines.length - readyLines.length
  const pendingReviewCount = visibleLines.filter((line) => (line.review_decision || 'pending') === 'pending').length
  const summary = batch?.summary || {}
  const totalLines = summary.total || lines.length

  if ((batch?.import_status || '') === 'processed') {
    return {
      statusKey: 'processed',
      label: 'Verwerkt',
      actionLabel: 'Openen',
      actionType: 'open',
      rank: 99,
      progressText: totalLines > 0 ? `${summary.processed || 0} verwerkt` : 'Afgerond',
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
    }
  }

  if ((batch?.import_status || '') === 'in_review' || (batch?.import_status || '') === 'reviewed' || selectedLines.length > 0 || pendingReviewCount < visibleLines.length) {
    return {
      statusKey: 'in_progress',
      label: 'In bewerking',
      actionLabel: 'Hervatten',
      actionType: 'resume',
      rank: 2,
      progressText: visibleLines.length > 0 ? `${readyLines.length} klaar / ${Math.max(visibleLines.length - readyLines.length, 0)} open` : 'Beoordeling loopt',
    }
  }

  return {
    statusKey: 'open',
    label: 'Open',
    actionLabel: 'Openen',
    actionType: 'open',
    rank: 3,
    progressText: totalLines > 0 ? `${totalLines} regel(s) wachten op beoordeling` : 'Nog te beoordelen',
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
