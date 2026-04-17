import { useEffect, useMemo, useRef, useState } from 'react'
import { ArticleGlobalSectionToggle, ArticleSectionAccordion } from '../components/ArticleSectionControls'
import useBarcodeScanner from '../../../lib/useBarcodeScanner'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../../lib/authSession'
import { getFieldsByTabAndGroup } from '../config/articleFieldHelpers'
import { ARTICLE_TABS } from '../config/articleFieldConstants'
import { resolveArticleFieldValue, EMPTY_VALUE } from '../lib/articleFieldValueResolver'
import { AUTO_CONSUME_MODES, fetchArticleAutoConsumeMode, getArticleAutoConsumeMode, saveArticleAutoConsumeMode } from '../services/articleAutomationOverrideService'
import { sortOptionObjects } from '../../../ui/sorting'

const GROUP_LABELS = {
  basic: 'Basis',
  external: 'Extern',
  nutrition_packaging: 'Voeding & verpakking',
  user: 'Gebruiker',
}


const EDITABLE_FORM_FIELDS = [
  { key: 'custom_name', label: 'Eigen naam', type: 'text', placeholder: 'Bijvoorbeeld: Pasta spaghetti' },
  { key: 'article_type', label: 'Artikeltype', type: 'text', placeholder: 'Bijvoorbeeld: Voedsel & drank' },
  { key: 'category', label: 'Categorie', type: 'text', placeholder: 'Bijvoorbeeld: Pasta & rijst' },
  { key: 'brand_or_maker', label: 'Merk / maker / aanbieder', type: 'text', placeholder: 'Bijvoorbeeld: De Cecco' },
  { key: 'short_description', label: 'Korte omschrijving', type: 'text', placeholder: 'Korte toelichting' },
  { key: 'barcode', label: 'Barcode', type: 'text', placeholder: 'Bijvoorbeeld: 8076800195057' },
  { key: 'article_number', label: 'Extern artikelnummer', type: 'text', placeholder: 'Bijvoorbeeld: BAR-8076800195057' },
]

const HOUSEHOLD_SETTINGS_STATUS_OPTIONS = [
  { value: 'active', label: 'Actief' },
  { value: 'inactive', label: 'Niet actief' },
]

function detectMobileScannerSupport() {
  if (typeof window === 'undefined') return false
  const coarse = window.matchMedia?.('(pointer: coarse)').matches
  const narrow = window.matchMedia?.('(max-width: 900px)').matches
  const mobileUA = /Android|iPhone|iPad|iPod/i.test(window.navigator.userAgent || '')
  return Boolean(coarse || narrow || mobileUA)
}

function FieldRow({ label, value }) {
  return (
    <div className="rz-field-row">
      <div className="rz-field-row-label">{label}:</div>
      <div className="rz-field-row-value">{value || EMPTY_VALUE}</div>
    </div>
  )
}

function humanizeSourceName(sourceName) {
  const key = String(sourceName || '').trim().toLowerCase()
  if (!key) return 'Onbekende bron'
  if (key === 'internal_catalog') return 'Interne productcatalogus'
  if (key === 'openfoodfacts' || key === 'open_food_facts') return 'Open Food Facts'
  if (key === 'public_reference' || key === 'public_reference_catalog') return 'Public reference catalog'
  if (key === 'gs1' || key === 'gs1_my_product_manager_share') return 'GS1 My Product Manager Share'
  return sourceName
}

function humanizeSourceStatus(status) {
  const key = String(status || '').trim().toLowerCase()
  if (!key) return 'onbekend'
  if (key === 'found' || key === 'success') return 'gevonden'
  if (key === 'not_found') return 'niet gevonden'
  if (key === 'failed' || key === 'error') return 'mislukt'
  if (key === 'skipped') return 'overgeslagen'
  if (key === 'pending') return 'in behandeling'
  if (key === 'low_confidence') return 'lage zekerheid'
  return status
}

function ProductSourceStatusList({ sourceChain = [], recentAttempts = [], enrichment = null, enrichmentStatus = null }) {
  const attemptsBySource = new Map()
  recentAttempts.forEach((attempt) => {
    const key = String(attempt?.source_name || '').trim().toLowerCase()
    if (!key || attemptsBySource.has(key)) return
    attemptsBySource.set(key, attempt)
  })
  const winningSource = String(enrichment?.source_name || enrichmentStatus?.source || enrichmentStatus?.last_lookup_source || '').trim().toLowerCase()

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {sourceChain.map((source) => {
        const key = String(source?.source_name || '').trim().toLowerCase()
        const configured = source?.configured !== false
        const enabled = source?.enabled !== false
        const attempt = attemptsBySource.get(key)
        const isWinner = Boolean(winningSource && winningSource === key)
        let state = 'Geen poging vastgelegd'
        let reason = ''

        if (!enabled) {
          state = 'Uitgeschakeld'
          reason = source?.notes || ''
        } else if (!configured) {
          state = 'Niet geconfigureerd'
          reason = source?.notes || ''
        } else if (attempt) {
          state = humanizeSourceStatus(attempt.status)
          reason = attempt?.message || ''
        } else if (isWinner) {
          state = 'Gekozen bron (hergebruikte data)'
          reason = 'De huidige productdata komt uit deze bron.'
        } else if (winningSource) {
          state = 'Niet gebruikt in laatste succesvolle lookup'
          reason = `Match gevonden via ${humanizeSourceName(winningSource)}.`
        }

        const metaParts = []
        if (attempt?.created_at) metaParts.push(`laatste poging: ${attempt.created_at}`)
        if (attempt?.normalized_barcode) metaParts.push(`barcode: ${attempt.normalized_barcode}`)
        if (attempt?.http_status) metaParts.push(`http: ${attempt.http_status}`)

        return (
          <div key={key || Math.random()} className="rz-field-row" style={{ alignItems: 'flex-start' }}>
            <div className="rz-field-row-label">{humanizeSourceName(source?.source_name)}:</div>
            <div className="rz-field-row-value">
              <div>{state}{isWinner ? ' — gekozen bron' : ''}</div>
              {reason ? <div style={{ marginTop: 2 }}>{reason}</div> : null}
              {metaParts.length ? <div style={{ marginTop: 2 }}>{metaParts.join(' · ')}</div> : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function normalizeFormValue(value, field) {
  if (field.type === 'number') {
    if (value === '' || value == null) return ''
    const parsed = Number(value)
    return Number.isFinite(parsed) ? String(parsed) : ''
  }
  return String(value || '')
}

function buildFormState(articleData = {}) {
  return EDITABLE_FORM_FIELDS.reduce((acc, field) => {
    let sourceValue = articleData?.[field.key]
    if (field.key === 'brand_or_maker') {
      sourceValue = articleData?.brand_or_maker ?? articleData?.brand ?? articleData?.maker ?? articleData?.provider ?? ''
    }
    acc[field.key] = normalizeFormValue(sourceValue, field)
    return acc
  }, {})
}

function isConsumable(articleData = {}) {
  if (articleData.consumable === true) return true
  return articleData.article_type === 'Voedsel & drank' || articleData.type === 'Voedsel & drank' || articleData.article_type === 'Huishoudelijk' || articleData.type === 'Huishoudelijk'
}

function AutomationOverrideCard({ articleData = {}, sectionOpen = undefined, onToggleSection = null }) {
  const articleId = articleData?.id
  const consumable = isConsumable(articleData)
  const [mode, setMode] = useState(AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD)
  const [saveMessage, setSaveMessage] = useState('')
  const dismissTimerRef = useRef(null)
  const automationOptions = useMemo(() => sortOptionObjects([
    { value: AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD, label: 'Huishoudinstelling volgen' },
    { value: AUTO_CONSUME_MODES.ALWAYS_ON, label: 'Altijd automatisch afboeken' },
    { value: AUTO_CONSUME_MODES.ALWAYS_OFF, label: 'Nooit automatisch afboeken' },
  ]), [])

  useEffect(() => {
    let cancelled = false
    setMode(getArticleAutoConsumeMode(articleId))
    setSaveMessage('')
    fetchArticleAutoConsumeMode(articleId).then((nextMode) => {
      if (!cancelled) setMode(nextMode)
    })
    return () => {
      cancelled = true
    }
  }, [articleId])

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current) {
        window.clearTimeout(dismissTimerRef.current)
      }
    }
  }, [])

  async function handleChange(event) {
    const nextMode = await saveArticleAutoConsumeMode(articleId, event.target.value)
    setMode(nextMode)
    setSaveMessage('Opgeslagen')
    if (dismissTimerRef.current) {
      window.clearTimeout(dismissTimerRef.current)
    }
    dismissTimerRef.current = window.setTimeout(() => setSaveMessage(''), 2400)
  }

  return (
    <ArticleSectionAccordion title="Automatisering" open={sectionOpen} onToggle={onToggleSection} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
      <div className="rz-article-automation-card">
        <div className="rz-article-automation-controls">
          <label className="rz-article-automation-field">
            <span className="rz-article-automation-label">Slim afboeken bij herhaalaankoop:</span>
            <select
              className="rz-article-automation-select"
              value={mode}
              onChange={handleChange}
              disabled={!consumable}
            >
              {automationOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          {saveMessage ? (
            <span className="rz-inline-feedback rz-inline-feedback--success rz-article-automation-feedback">{saveMessage}</span>
          ) : null}
        </div>
      </div>
    </ArticleSectionAccordion>
  )
}

function EditableHouseholdFieldRow({ field, value, draftValue, onChange, onBlur, onKeyDown, isSaving, canEdit }) {
  const sharedProps = {
    className: 'rz-input rz-article-inline-input',
    value: draftValue,
    placeholder: field.placeholder,
    onChange: (event) => onChange(field.key, event.target.value),
    onBlur: () => onBlur(field.key),
    onKeyDown: (event) => onKeyDown(event, field.key),
    disabled: !canEdit || isSaving,
    'data-testid': `article-details-input-${field.key}`,
  }

  return (
    <div className="rz-field-row rz-field-row--editable" data-testid={`article-inline-row-${field.key}`}>
      <label className="rz-field-row-label" htmlFor={`article-inline-input-${field.key}`}>{field.label}:</label>
      <div className="rz-field-row-value rz-field-row-value--editable">
        {field.type === 'textarea' ? (
          <textarea
            id={`article-inline-input-${field.key}`}
            rows={3}
            {...sharedProps}
          />
        ) : (
          <input
            id={`article-inline-input-${field.key}`}
            type={field.type}
            step={field.step}
            {...sharedProps}
          />
        )}
      </div>
    </div>
  )
}

function ArticleDetailsEditor({ articleData = {}, onDetailsSaved = null, sectionOpen = undefined, onToggleSection = null }) {
  const authContext = readStoredAuthContext() || {}
  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()
  const canEdit = displayRole === 'admin' || displayRole === 'lid'
  const [formState, setFormState] = useState(() => buildFormState(articleData))
  const [statusMessage, setStatusMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [savingFieldKey, setSavingFieldKey] = useState('')

  useEffect(() => {
    setFormState(buildFormState(articleData))
    setStatusMessage('')
    setErrorMessage('')
    setSavingFieldKey('')
  }, [articleData?.name, articleData?.custom_name, articleData?.article_type, articleData?.category, articleData?.brand_or_maker, articleData?.brand, articleData?.short_description, articleData?.notes, articleData?.min_stock, articleData?.ideal_stock, articleData?.favorite_store, articleData?.barcode, articleData?.article_number])

  function updateField(key, value) {
    setFormState((current) => ({ ...current, [key]: value }))
  }

  function currentFieldValue(field) {
    if (field.key === 'brand_or_maker') {
      return normalizeFormValue(articleData?.brand_or_maker ?? articleData?.brand ?? articleData?.maker ?? articleData?.provider ?? '', field)
    }
    return normalizeFormValue(articleData?.[field.key], field)
  }

  async function persistField(fieldKey) {
    const field = EDITABLE_FORM_FIELDS.find((item) => item.key === fieldKey)
    const resolvedArticleId = articleData?.article_id || articleData?.id
    const resolvedArticleName = articleData?.article_name || articleData?.name
    if (!field || !canEdit || (!resolvedArticleId && !resolvedArticleName)) return
    const nextValue = normalizeFormValue(formState[fieldKey], field)
    const previousValue = currentFieldValue(field)
    if (nextValue === previousValue) return

    setSavingFieldKey(fieldKey)
    setStatusMessage('')
    setErrorMessage('')
    try {
      const payload = {
        custom_name: formState.custom_name.trim(),
        article_type: formState.article_type.trim(),
        category: formState.category.trim(),
        brand_or_maker: formState.brand_or_maker.trim(),
        short_description: formState.short_description.trim(),
        favorite_store: formState.favorite_store.trim(),
        notes: formState.notes.trim(),
        barcode: formState.barcode.trim(),
        article_number: formState.article_number.trim(),
        min_stock: formState.min_stock === '' ? null : Number(formState.min_stock),
        ideal_stock: formState.ideal_stock === '' ? null : Number(formState.ideal_stock),
      }
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(String(resolvedArticleId))}`, {
        method: 'PATCH',
        body: JSON.stringify(payload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data?.detail || 'Artikeldetails konden niet worden opgeslagen.')
      }
      const nextDetails = data?.details && typeof data.details === 'object' ? data.details : { ...articleData, ...payload }
      setFormState(buildFormState(nextDetails))
      if (typeof onDetailsSaved === 'function') onDetailsSaved(nextDetails)
      setStatusMessage(`'${field.label}' opgeslagen.`)
    } catch (error) {
      setErrorMessage(error?.message || 'Artikeldetails konden niet worden opgeslagen.')
      setFormState((current) => ({ ...current, [fieldKey]: previousValue }))
    } finally {
      setSavingFieldKey('')
    }
  }

  function handleKeyDown(event, fieldKey) {
    if (event.key === 'Enter' && event.target.tagName !== 'TEXTAREA') {
      event.preventDefault()
      event.currentTarget.blur()
    }
  }

  return (
    <ArticleSectionAccordion title="Artikelgegevens voor dit huishouden" testId="article-household-details-section" open={sectionOpen} onToggle={onToggleSection} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
      <div className="rz-article-overview-instruction">Wijzigingen worden opgeslagen bij verlaten van een veld.</div>
      {statusMessage ? <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="article-details-save-success">{statusMessage}</div> : null}
      {errorMessage ? <div className="rz-article-detail-alert" data-testid="article-details-save-error">{errorMessage}</div> : null}
      <div style={{ display: 'grid', gap: 8 }}>
        {EDITABLE_FORM_FIELDS.map((field) => (
          <EditableHouseholdFieldRow
            key={field.key}
            field={field}
            value={currentFieldValue(field)}
            draftValue={formState[field.key]}
            onChange={updateField}
            onBlur={persistField}
            onKeyDown={handleKeyDown}
            isSaving={savingFieldKey === field.key}
            canEdit={canEdit}
          />
        ))}
      </div>
    </ArticleSectionAccordion>
  )
}


function normalizeSettingsFormValue(value, type = 'text') {
  if (type === 'number') {
    if (value === '' || value == null) return ''
    const parsed = Number(value)
    return Number.isFinite(parsed) ? String(parsed) : ''
  }
  if (type === 'checkbox') return Boolean(value)
  return String(value || '')
}

function buildHouseholdSettingsFormState(settings = {}) {
  return {
    min_stock: normalizeSettingsFormValue(settings?.min_stock, 'number'),
    ideal_stock: normalizeSettingsFormValue(settings?.ideal_stock, 'number'),
    favorite_store: normalizeSettingsFormValue(settings?.favorite_store),
    average_price: normalizeSettingsFormValue(settings?.average_price, 'number'),
    status: normalizeSettingsFormValue(settings?.status || 'active'),
    default_location_id: normalizeSettingsFormValue(settings?.default_location_id),
    default_sublocation_id: normalizeSettingsFormValue(settings?.default_sublocation_id),
    auto_restock: normalizeSettingsFormValue(settings?.auto_restock, 'checkbox'),
    packaging_unit: normalizeSettingsFormValue(settings?.packaging_unit),
    packaging_quantity: normalizeSettingsFormValue(settings?.packaging_quantity, 'number'),
    notes: normalizeSettingsFormValue(settings?.notes),
  }
}

function HouseholdArticleSettingsCard({ articleData = {}, onDetailsSaved = null, sectionOpen = undefined, onToggleSection = null }) {
  const authContext = readStoredAuthContext() || {}
  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()
  const canEdit = displayRole === 'admin' || displayRole === 'lid'
  const resolvedArticleId = String(articleData?.household_article_id || articleData?.article_id || articleData?.id || '').trim()
  const settings = articleData?.settings && typeof articleData.settings === 'object' ? articleData.settings : {}
  const [formState, setFormState] = useState(() => buildHouseholdSettingsFormState(settings))
  const [statusMessage, setStatusMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isLoadingLocations, setIsLoadingLocations] = useState(false)
  const [locationOptions, setLocationOptions] = useState([])
  const [sublocationOptions, setSublocationOptions] = useState([])

  useEffect(() => {
    setFormState(buildHouseholdSettingsFormState(settings))
    setStatusMessage('')
    setErrorMessage('')
  }, [
    settings?.min_stock,
    settings?.ideal_stock,
    settings?.favorite_store,
    settings?.average_price,
    settings?.status,
    settings?.default_location_id,
    settings?.default_sublocation_id,
    settings?.auto_restock,
    settings?.packaging_unit,
    settings?.packaging_quantity,
    settings?.notes,
  ])

  useEffect(() => {
    let cancelled = false
    async function loadLocations() {
      setIsLoadingLocations(true)
      try {
        const [spacesResponse, sublocationsResponse] = await Promise.all([
          fetchJsonWithAuth('/api/spaces'),
          fetchJsonWithAuth('/api/sublocations'),
        ])
        const spacesData = await spacesResponse.json().catch(() => ({}))
        const sublocationsData = await sublocationsResponse.json().catch(() => ({}))
        if (!spacesResponse.ok) throw new Error(spacesData?.detail || 'Ruimtes konden niet worden geladen.')
        if (!sublocationsResponse.ok) throw new Error(sublocationsData?.detail || 'Sublocaties konden niet worden geladen.')
        if (cancelled) return
        const nextSpaces = (Array.isArray(spacesData?.items) ? spacesData.items : []).filter((item) => item?.active !== false)
        const nextSublocations = (Array.isArray(sublocationsData?.items) ? sublocationsData.items : []).filter((item) => item?.active !== false)
        setLocationOptions(nextSpaces)
        setSublocationOptions(nextSublocations)
      } catch (error) {
        if (!cancelled) setErrorMessage(error?.message || 'Locatie-opties konden niet worden geladen.')
      } finally {
        if (!cancelled) setIsLoadingLocations(false)
      }
    }
    loadLocations()
    return () => {
      cancelled = true
    }
  }, [])

  const visibleSublocations = useMemo(() => {
    return sublocationOptions.filter((item) => String(item?.space_id || '') === String(formState.default_location_id || ''))
  }, [sublocationOptions, formState.default_location_id])

  function updateField(key, value) {
    setFormState((current) => {
      const next = { ...current, [key]: value }
      if (key === 'default_location_id') {
        const stillValid = visibleSublocations.some((item) => String(item?.id || '') === String(current.default_sublocation_id || ''))
        next.default_sublocation_id = stillValid && String(value || '') === String(current.default_location_id || '') ? current.default_sublocation_id : ''
      }
      return next
    })
  }

  async function handleSave() {
    if (!resolvedArticleId || !canEdit) return
    setIsSaving(true)
    setStatusMessage('')
    setErrorMessage('')
    try {
      const payload = {
        min_stock: formState.min_stock === '' ? null : Number(formState.min_stock),
        ideal_stock: formState.ideal_stock === '' ? null : Number(formState.ideal_stock),
        favorite_store: formState.favorite_store.trim(),
        average_price: formState.average_price === '' ? null : Number(formState.average_price),
        status: formState.status || 'active',
        default_location_id: formState.default_location_id || null,
        default_sublocation_id: formState.default_sublocation_id || null,
        auto_restock: Boolean(formState.auto_restock),
        packaging_unit: formState.packaging_unit.trim(),
        packaging_quantity: formState.packaging_quantity === '' ? null : Number(formState.packaging_quantity),
        notes: formState.notes.trim(),
      }
      const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(resolvedArticleId)}/settings`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Huishoudinstellingen konden niet worden opgeslagen.')
      const nextSettings = data?.settings && typeof data.settings === 'object' ? data.settings : payload
      setFormState(buildHouseholdSettingsFormState(nextSettings))
      if (typeof onDetailsSaved === 'function') onDetailsSaved({ settings: nextSettings })
      setStatusMessage('Instellingen voor dit huishouden opgeslagen.')
    } catch (error) {
      setErrorMessage(error?.message || 'Huishoudinstellingen konden niet worden opgeslagen.')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <ArticleSectionAccordion title="Instellingen voor dit huishouden" testId="article-household-settings-section" open={sectionOpen} onToggle={onToggleSection} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
      <div className="rz-article-overview-instruction">Deze instellingen gelden alleen voor dit huishouden en blijven na opslaan behouden.</div>
      {statusMessage ? <div className="rz-inline-feedback rz-inline-feedback--success" data-testid="article-settings-save-success">{statusMessage}</div> : null}
      {errorMessage ? <div className="rz-article-detail-alert" data-testid="article-settings-save-error">{errorMessage}</div> : null}
      <div style={{ display: 'grid', gap: 8 }}>
        <EditableHouseholdFieldRow field={{ key: 'min_stock', label: 'Minimumvoorraad', type: 'number', placeholder: '0', step: '0.1' }} draftValue={formState.min_stock} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <EditableHouseholdFieldRow field={{ key: 'ideal_stock', label: 'Streefvoorraad', type: 'number', placeholder: '0', step: '0.1' }} draftValue={formState.ideal_stock} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <EditableHouseholdFieldRow field={{ key: 'favorite_store', label: 'Voorkeurswinkel', type: 'text', placeholder: 'Bijvoorbeeld: Jumbo' }} draftValue={formState.favorite_store} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <EditableHouseholdFieldRow field={{ key: 'average_price', label: 'Prijsindicatie', type: 'number', placeholder: '0', step: '0.01' }} draftValue={formState.average_price} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <div className="rz-field-row rz-field-row--editable">
          <label className="rz-field-row-label" htmlFor="article-household-settings-status">Status:</label>
          <div className="rz-field-row-value rz-field-row-value--editable">
            <select id="article-household-settings-status" className="rz-input rz-article-inline-input" value={formState.status} onChange={(event) => updateField('status', event.target.value)} disabled={!canEdit || isSaving} data-testid="article-household-settings-status">
              {HOUSEHOLD_SETTINGS_STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </div>
        </div>
        <div className="rz-field-row rz-field-row--editable">
          <label className="rz-field-row-label" htmlFor="article-household-settings-location">Standaardruimte:</label>
          <div className="rz-field-row-value rz-field-row-value--editable">
            <select id="article-household-settings-location" className="rz-input rz-article-inline-input" value={formState.default_location_id} onChange={(event) => updateField('default_location_id', event.target.value)} disabled={!canEdit || isSaving || isLoadingLocations} data-testid="article-household-settings-location">
              <option value="">Geen standaardruimte</option>
              {locationOptions.map((option) => <option key={option.id} value={option.id}>{option.naam}</option>)}
            </select>
          </div>
        </div>
        <div className="rz-field-row rz-field-row--editable">
          <label className="rz-field-row-label" htmlFor="article-household-settings-sublocation">Standaardsublocatie:</label>
          <div className="rz-field-row-value rz-field-row-value--editable">
            <select id="article-household-settings-sublocation" className="rz-input rz-article-inline-input" value={formState.default_sublocation_id} onChange={(event) => updateField('default_sublocation_id', event.target.value)} disabled={!canEdit || isSaving || isLoadingLocations || !formState.default_location_id} data-testid="article-household-settings-sublocation">
              <option value="">Geen standaardsublocatie</option>
              {visibleSublocations.map((option) => <option key={option.id} value={option.id}>{option.naam}</option>)}
            </select>
          </div>
        </div>
        <div className="rz-field-row rz-field-row--editable">
          <label className="rz-field-row-label" htmlFor="article-household-settings-auto-restock">Automatisch aanvullen:</label>
          <div className="rz-field-row-value rz-field-row-value--editable">
            <input id="article-household-settings-auto-restock" type="checkbox" checked={Boolean(formState.auto_restock)} onChange={(event) => updateField('auto_restock', event.target.checked)} disabled={!canEdit || isSaving} data-testid="article-household-settings-auto-restock" />
          </div>
        </div>
        <EditableHouseholdFieldRow field={{ key: 'packaging_unit', label: 'Verpakkingseenheid', type: 'text', placeholder: 'Bijvoorbeeld: pak' }} draftValue={formState.packaging_unit} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <EditableHouseholdFieldRow field={{ key: 'packaging_quantity', label: 'Verpakkingshoeveelheid', type: 'number', placeholder: '1', step: '0.1' }} draftValue={formState.packaging_quantity} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
        <EditableHouseholdFieldRow field={{ key: 'notes', label: 'Notities', type: 'textarea', placeholder: 'Eigen notities voor dit huishouden' }} draftValue={formState.notes} onChange={updateField} onBlur={() => {}} onKeyDown={() => {}} isSaving={isSaving} canEdit={canEdit} />
      </div>
      <div className="rz-article-inline-actions" style={{ marginTop: 12 }}>
        <button type="button" className="rz-button-primary rz-button-small" onClick={handleSave} disabled={!canEdit || isSaving || !resolvedArticleId} data-testid="article-household-settings-save">{isSaving ? 'Opslaan…' : 'Opslaan'}</button>
      </div>
    </ArticleSectionAccordion>
  )
}

function ProductDetailsCard({ articleData = {}, sectionOpen = undefined, onToggleSection = null }) {
  const identity = articleData?.product_details?.identity || {}
  const internalCatalog = articleData?.product_details?.internal_catalog || {}
  const enrichment = articleData?.product_details?.enrichment || null
  const enrichmentStatus = articleData?.product_details?.enrichment_status || {}
  const sourceChain = Array.isArray(articleData?.product_details?.source_chain) ? articleData.product_details.source_chain : []
  const sourceChainLabel = sourceChain
    .map((source) => {
      const name = humanizeSourceName(source?.source_name)
      if (!name) return ''
      if (source?.configured === false) return `${name} (nog niet geconfigureerd)`
      if (source?.enabled === false) return `${name} (uit)`
      return `${name} (actief)`
    })
    .filter(Boolean)
    .join(' → ')
  const recentAttempts = Array.isArray(articleData?.product_details?.recent_enrichment_attempts)
    ? articleData.product_details.recent_enrichment_attempts
    : []
  const recentAttemptsLabel = recentAttempts
    .slice(0, 3)
    .map((attempt) => {
      const source = humanizeSourceName(attempt?.source_name)
      const status = humanizeSourceStatus(attempt?.status)
      const createdAt = String(attempt?.created_at || '').trim()
      return createdAt ? `${source}: ${status} (${createdAt})` : `${source}: ${status}`
    })
    .join(' | ')
  const winningSource = humanizeSourceName(enrichment?.source_name || enrichmentStatus?.source || enrichmentStatus?.last_lookup_source)
  const matchStatus = humanizeSourceStatus(enrichmentStatus?.status || enrichment?.lookup_status)
  const lookupMessage = enrichmentStatus?.message || enrichmentStatus?.last_lookup_message
  const retrievalMode = recentAttempts.length ? 'Nieuwe lookup vastgelegd in audit' : (winningSource && enrichment?.fetched_at ? 'Hergebruik van eerder verrijkte productdata' : '')

  return (
    <ArticleSectionAccordion title="Productverrijking" testId="article-product-enrichment-section" open={sectionOpen} onToggle={onToggleSection} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
      <FieldRow label="Bronketen" value={sourceChainLabel} />
      <FieldRow label="Interne matchstatus" value={internalCatalog?.status} />
      <FieldRow label="Centrale product-ID" value={internalCatalog?.global_product_id} />
      <FieldRow label="Hergebruik uit productcatalogus" value={internalCatalog?.reused_from_catalog ? 'ja' : 'nee'} />
      <FieldRow label="Gekozen bron" value={winningSource} />
      <FieldRow label="Matchstatus" value={matchStatus} />
      <FieldRow label="Gebruiksmodus" value={retrievalMode} />
      <FieldRow label="Recente bronpogingen" value={recentAttemptsLabel} />
      <ProductSourceStatusList sourceChain={sourceChain} recentAttempts={recentAttempts} enrichment={enrichment} enrichmentStatus={enrichmentStatus} />
      <FieldRow label="Primaire identiteit" value={identity?.identity_type} />
      <FieldRow label="Waarde" value={identity?.identity_value} />
      <FieldRow label="Genormaliseerde barcode" value={identity?.normalized_barcode || enrichmentStatus?.normalized_barcode} />
      <FieldRow label="Bron identiteit" value={humanizeSourceName(identity?.source)} />
      <FieldRow label="Confidence" value={identity?.confidence_score != null ? String(identity.confidence_score) : ''} />
      <FieldRow label="Verrijkingsstatus" value={matchStatus} />
      <FieldRow label="Bron lookup" value={winningSource} />
      <FieldRow label="Lookup melding" value={lookupMessage} />
      <FieldRow label="Laatste lookup" value={enrichmentStatus?.lookup_attempted_at || enrichment?.last_lookup_at || enrichment?.fetched_at} />
      <FieldRow label="Titel" value={enrichment?.title} />
      <FieldRow label="Merk" value={enrichment?.brand} />
      <FieldRow label="Categorie" value={enrichment?.category} />
      <FieldRow label="Inhoud" value={enrichment?.size_value != null ? `${enrichment.size_value}${enrichment?.size_unit ? ` ${enrichment.size_unit}` : ''}` : ''} />
      <FieldRow label="Ingrediënten" value={Array.isArray(enrichment?.ingredients) ? enrichment.ingredients.join(', ') : ''} />
      <FieldRow label="Allergenen" value={Array.isArray(enrichment?.allergens) ? enrichment.allergens.join(', ') : ''} />
      <FieldRow label="Laatst opgehaald" value={enrichment?.fetched_at} />
      <FieldRow label="Bron productdata" value={humanizeSourceName(enrichment?.source_name)} />
    </ArticleSectionAccordion>
  )
}


function ExternalLinkCard({ articleData = {}, onDetailsSaved = null, sectionOpen = undefined, onToggleSection = null }) {
  const isMobileScanner = useMemo(() => detectMobileScannerSupport(), [])
  const [editMode, setEditMode] = useState(false)
  const [showOverwriteConfirm, setShowOverwriteConfirm] = useState(false)
  const [formState, setFormState] = useState({ barcode: articleData?.barcode || '', article_number: articleData?.article_number || '' })
  const [saveState, setSaveState] = useState({ saving: false, message: '', error: '' })
  const {
    videoRef,
    isOpen: scannerOpen,
    cameraState: scanState,
    cameraMeta,
    availableCameras,
    startScanner,
    stopScanner,
    switchCamera,
  } = useBarcodeScanner({
    screenContext: 'Artikeldetail',
    onDetected: async (detected, scannerContext = {}) => {
      const { logEvent } = scannerContext
      logEvent?.('BARCODE_NORMALIZED', { normalizedBarcode: String(detected || '').trim() })
      logEvent?.('BARCODE_FIELD_BEFORE_UPDATE', { value: String(formState.barcode || '') })
      setFormState((current) => {
        const next = { ...current, barcode: detected }
        logEvent?.('BARCODE_FIELD_UPDATED', { value: String(next.barcode || '') })
        return next
      })
      await persistExternalLink({ barcode: detected }, scannerContext)
      logEvent?.('BARCODE_FIELD_AFTER_UPDATE', { value: String(detected || '') })
    },
  })

  useEffect(() => {
    setFormState({ barcode: articleData?.barcode || '', article_number: articleData?.article_number || '' })
  }, [articleData?.barcode, articleData?.article_number])

  async function refreshDetails() {
    if (typeof onDetailsSaved !== 'function') return
    const detailId = articleData?.article_id || articleData?.id || articleData?.inventory_id
    if (!detailId) return
    const stableArticleId = String(detailId).trim()
    const endpoint = stableArticleId.startsWith('article::') || stableArticleId.startsWith('live::')
      ? `/api/inventory/${encodeURIComponent(stableArticleId)}/article-detail`
      : `/api/household-articles/${encodeURIComponent(stableArticleId)}`
    const refreshResponse = await fetchJsonWithAuth(endpoint)
    const refreshed = await refreshResponse.json().catch(() => null)
    if (refreshResponse.ok && refreshed) onDetailsSaved(refreshed)
  }

  async function triggerImmediateEnrichment() {
    const articleId = articleData?.article_id || articleData?.id
    if (!articleId) return null
    const response = await fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(articleId)}/enrich`, {
      method: 'POST',
      body: JSON.stringify({ force_refresh: true }),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data?.detail || 'Productverrijking kon niet worden gestart.')
    }
    return response.json().catch(() => null)
  }

  async function startScannerWithDevice(deviceId = '') {
    await startScanner(deviceId)
  }

  function closeScanner(preserveMessage = false) {
    stopScanner(preserveMessage)
  }

  async function handleSwitchCamera() {
    await switchCamera()
  }

  async function persistExternalLink(partial = {}, scannerContext = {}) {
    const inventoryId = articleData?.inventory_id || articleData?.article_id || articleData?.id
    if (!inventoryId) return
    const nextPayload = {
      barcode: String(partial.barcode ?? formState.barcode ?? '').trim(),
      article_number: String(partial.article_number ?? formState.article_number ?? '').trim(),
    }
    setSaveState({ saving: true, message: '', error: '' })
    const { logEvent } = scannerContext
    try {
      const response = await fetchJsonWithAuth(`/api/inventory/${encodeURIComponent(inventoryId)}/external-product-link`, {
        method: 'POST',
        body: JSON.stringify(nextPayload),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Externe productkoppeling kon niet worden opgeslagen.')
      const persistedDetails = data?.details && typeof data.details === 'object' ? data.details : {}
      const persistedBarcode = persistedDetails?.barcode || nextPayload.barcode
      const persistedArticleNumber = persistedDetails?.article_number || nextPayload.article_number
      const optimisticDetails = { ...articleData, ...persistedDetails, barcode: persistedBarcode, article_number: persistedArticleNumber }
      setFormState({ barcode: persistedBarcode, article_number: persistedArticleNumber })
      if (typeof onDetailsSaved === 'function') onDetailsSaved(optimisticDetails)
      logEvent?.('ENRICH_TRIGGERED', { barcode: persistedBarcode })
      await triggerImmediateEnrichment()
      await refreshDetails()
      setSaveState({ saving: false, message: 'Opgeslagen', error: '' })
    } catch (error) {
      setSaveState({ saving: false, message: '', error: error?.message || 'Externe productkoppeling kon niet worden opgeslagen.' })
    }
  }

  function hasExistingValue() {
    return Boolean(String(articleData?.barcode || '').trim() || String(articleData?.article_number || '').trim())
  }

  function handleEnableManualEntry() {
    if (hasExistingValue()) {
      setShowOverwriteConfirm(true)
      return
    }
    setEditMode(true)
  }

  function confirmOverwrite(allow) {
    setShowOverwriteConfirm(false)
    if (allow) setEditMode(true)
  }

  async function handleFieldBlur(fieldKey) {
    if (!editMode) return
    const currentValue = String(articleData?.[fieldKey] || '').trim()
    const nextValue = String(formState?.[fieldKey] || '').trim()
    if (currentValue === nextValue) return
    await persistExternalLink({ [fieldKey]: nextValue })
  }

  async function handleOpenScanner() {
    if (!isMobileScanner) return
    await startScannerWithDevice(cameraMeta.deviceId)
  }

  const actions = (

    <>
      {isMobileScanner ? <button type="button" className="rz-button-secondary rz-button-small" onClick={handleOpenScanner} data-testid="article-external-link-scan">Barcode scannen</button> : null}
      <button type="button" className="rz-button-secondary rz-button-small" onClick={handleEnableManualEntry} data-testid="article-external-link-edit">Barcode invullen</button>
    </>
  )

  return (
    <ArticleSectionAccordion title="Externe productkoppeling" testId="article-external-link-section" headerActions={actions} open={sectionOpen} onToggle={onToggleSection} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
      {showOverwriteConfirm ? (
        <div className="rz-article-detail-alert rz-article-detail-alert--warning">
          <div>Er staat al een waarde ingevuld. Alsnog overschrijven?</div>
          <div className="rz-article-inline-actions rz-article-inline-actions--tight">
            <button type="button" className="rz-button-secondary rz-button-small" onClick={() => confirmOverwrite(true)}>Ja</button>
            <button type="button" className="rz-button-secondary rz-button-small" onClick={() => confirmOverwrite(false)}>Nee</button>
          </div>
        </div>
      ) : null}
      {saveState.message ? <div className="rz-inline-feedback rz-inline-feedback--success">{saveState.message}</div> : null}
      {saveState.error ? <div className="rz-inline-feedback rz-inline-feedback--danger">{saveState.error}</div> : null}
      {!isMobileScanner ? <div className="rz-inline-feedback">Gebruik op laptop/desktop de handmatige barcode-invoer. Live scannen is alleen beschikbaar op mobiel.</div> : null}
      {scanState.status === 'error' ? <div className="rz-inline-feedback rz-inline-feedback--danger">{scanState.message}</div> : null}
      {isMobileScanner ? (
        <div className="rz-barcode-scan-panel" style={{ display: scannerOpen ? 'block' : 'none' }}>
          <video ref={videoRef} className="rz-barcode-scan-video" autoPlay muted playsInline style={{ visibility: scannerOpen ? 'visible' : 'hidden' }} />
          <div className="rz-article-inline-actions rz-article-inline-actions--tight rz-barcode-scan-toolbar">
            <span className="rz-inline-feedback">{scanState.message}</span>
            <div className="rz-article-inline-actions rz-article-inline-actions--tight rz-barcode-scan-toolbar-actions">
              <button type="button" className="rz-button-secondary rz-button-small" onClick={handleSwitchCamera} disabled={availableCameras.length < 2}>Camera wisselen</button>
              <button type="button" className="rz-button-secondary rz-button-small" onClick={() => closeScanner(true)}>Camera sluiten</button>
            </div>
          </div>
          <div className="rz-inline-feedback" style={{ marginTop: 8 }}>
            Camera: {cameraMeta.label || cameraMeta.deviceId || 'onbekend'} · Decodepogingen: {cameraMeta.decodeAttempts}
          </div>
        </div>
      ) : null}
      <div className="rz-field-row">
        <div className="rz-field-row-label">Barcode:</div>
        <div className="rz-field-row-value rz-field-row-value--editable">
          {editMode ? (
            <input
              className="rz-input rz-article-inline-input"
              value={formState.barcode}
              onChange={(event) => setFormState((current) => ({ ...current, barcode: event.target.value }))}
              onBlur={() => handleFieldBlur('barcode')}
              disabled={saveState.saving}
              data-testid="article-external-link-input-barcode"
            />
          ) : (articleData?.barcode || EMPTY_VALUE)}
        </div>
      </div>
      <div className="rz-field-row">
        <div className="rz-field-row-label">Extern artikelnummer:</div>
        <div className="rz-field-row-value rz-field-row-value--editable">
          {editMode ? (
            <input
              className="rz-input rz-article-inline-input"
              value={formState.article_number}
              onChange={(event) => setFormState((current) => ({ ...current, article_number: event.target.value }))}
              onBlur={() => handleFieldBlur('article_number')}
              disabled={saveState.saving}
              data-testid="article-external-link-input-article-number"
            />
          ) : (articleData?.article_number || EMPTY_VALUE)}
        </div>
      </div>
      <FieldRow label="Bron" value={articleData?.source} />
    </ArticleSectionAccordion>
  )
}

export default function ArticleOverviewTab({ articleData = {}, visibilityMap = {}, visibilityLoading = false, visibilityError = null, onDetailsSaved = null }) {
  const groupedFields = useMemo(() => getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW), [])
  const overviewVisibility = visibilityMap?.overview || {}
  const sectionIds = useMemo(() => {
    const baseIds = [
      'article-details',
      'household-settings',
      'external-link',
      'product-enrichment',
      'automation-override',
    ]
    return [...baseIds, ...Object.keys(groupedFields).map((groupKey) => `group-${groupKey}`)]
  }, [groupedFields])
  const [sectionStates, setSectionStates] = useState({})

  const visibleGroups = useMemo(() => {
    return Object.entries(groupedFields).reduce((acc, [groupKey, fields]) => {
      const visible = fields.filter((field) => overviewVisibility[field.key] === true)
      if (visible.length > 0) acc[groupKey] = visible
      return acc
    }, {})
  }, [groupedFields, overviewVisibility])

  useEffect(() => {
    setSectionStates((current) => {
      const next = {}
      sectionIds.forEach((sectionId) => {
        next[sectionId] = Object.prototype.hasOwnProperty.call(current, sectionId) ? current[sectionId] : true
      })
      return next
    })
  }, [sectionIds])

  const visibleGroupSectionIds = useMemo(
    () => Object.keys(visibleGroups).map((groupKey) => `group-${groupKey}`),
    [visibleGroups],
  )

  const activeSectionIds = useMemo(
    () => [
      'article-details',
      'household-settings',
      'external-link',
      'product-enrichment',
      'automation-override',
      ...visibleGroupSectionIds,
    ],
    [visibleGroupSectionIds],
  )

  const canExpandAll = activeSectionIds.some((sectionId) => sectionStates[sectionId] === false)
  const canCollapseAll = activeSectionIds.some((sectionId) => sectionStates[sectionId] !== false)

  function toggleSection(sectionId) {
    setSectionStates((current) => ({ ...current, [sectionId]: !current[sectionId] }))
  }

  if (visibilityLoading) {
    return <div className="rz-empty-state">Overzichtsvelden worden geladen.</div>
  }

  if (Object.keys(visibleGroups).length === 0) {
    return <div className="rz-empty-state">Er zijn geen zichtbare velden ingesteld voor Overzicht.</div>
  }

  function expandAllSections() {
    setSectionStates((current) => activeSectionIds.reduce((acc, sectionId) => ({ ...acc, [sectionId]: true }), { ...current }))
  }

  function collapseAllSections() {
    setSectionStates((current) => activeSectionIds.reduce((acc, sectionId) => ({ ...acc, [sectionId]: false }), { ...current }))
  }

  return (
    <div className="rz-overview-tab">
      {visibilityError ? <div className="rz-article-detail-alert">Veldinstellingen konden niet volledig worden geladen. Standaardvelden worden getoond.</div> : null}
      <ArticleGlobalSectionToggle ariaLabelPrefix="Overzicht" onExpandAll={expandAllSections} onCollapseAll={collapseAllSections} canExpand={canExpandAll} canCollapse={canCollapseAll} />
      <ArticleDetailsEditor articleData={articleData} onDetailsSaved={onDetailsSaved} sectionOpen={sectionStates['article-details']} onToggleSection={() => toggleSection('article-details')} />
      <HouseholdArticleSettingsCard articleData={articleData} onDetailsSaved={onDetailsSaved} sectionOpen={sectionStates['household-settings']} onToggleSection={() => toggleSection('household-settings')} />
      <ExternalLinkCard articleData={articleData} onDetailsSaved={onDetailsSaved} sectionOpen={sectionStates['external-link']} onToggleSection={() => toggleSection('external-link')} />
      <ProductDetailsCard articleData={articleData} sectionOpen={sectionStates['product-enrichment']} onToggleSection={() => toggleSection('product-enrichment')} />
      <AutomationOverrideCard articleData={articleData} sectionOpen={sectionStates['automation-override']} onToggleSection={() => toggleSection('automation-override')} />
      {Object.entries(visibleGroups).map(([groupKey, fields]) => (
        <ArticleSectionAccordion key={groupKey} title={GROUP_LABELS[groupKey] || groupKey} open={sectionStates[`group-${groupKey}`]} onToggle={() => toggleSection(`group-${groupKey}`)} sectionClassName="rz-overview-group rz-article-detail-section" titleClassName="rz-overview-group-title rz-article-detail-section-title" contentClassName="rz-overview-group-body rz-article-detail-section-body">
          {fields.map((field) => (
            <FieldRow key={field.key} label={field.label} value={resolveArticleFieldValue(field.key, articleData)} />
          ))}
        </ArticleSectionAccordion>
      ))}
    </div>
  )
}
