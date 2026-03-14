import { useEffect, useMemo, useRef, useState } from 'react'
import { getFieldsByTabAndGroup } from '../config/articleFieldHelpers'
import { ARTICLE_TABS } from '../config/articleFieldConstants'
import { resolveArticleFieldValue, EMPTY_VALUE } from '../lib/articleFieldValueResolver'
import { AUTO_CONSUME_MODES, fetchArticleAutoConsumeMode, getArticleAutoConsumeMode, saveArticleAutoConsumeMode } from '../services/articleAutomationOverrideService'

const GROUP_LABELS = {
  basic: 'Basis',
  external: 'Extern',
  nutrition_packaging: 'Voeding & verpakking',
  user: 'Gebruiker',
}

function FieldRow({ label, value }) {
  return (
    <div className="rz-field-row">
      <div className="rz-field-row-label">{label}</div>
      <div className="rz-field-row-value">{value || EMPTY_VALUE}</div>
    </div>
  )
}


function isConsumable(articleData = {}) {
  if (articleData.consumable === true) return true
  return articleData.article_type === 'Voedsel & drank' || articleData.type === 'Voedsel & drank' || articleData.article_type === 'Huishoudelijk' || articleData.type === 'Huishoudelijk'
}

function AutomationOverrideCard({ articleData = {} }) {
  const articleId = articleData?.id
  const consumable = isConsumable(articleData)
  const [mode, setMode] = useState(AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD)
  const [saveMessage, setSaveMessage] = useState('')
  const dismissTimerRef = useRef(null)

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
    <section className="rz-overview-group">
      <div className="rz-article-automation-card">
        <div className="rz-article-automation-copy">
          <h3 className="rz-overview-group-title rz-article-automation-title">Automatisering</h3>
          <p className="rz-article-automation-text">
            Bepaal per artikel welke automatische afboekstrategie geldt bij een nieuwe aankoop van een verbruiksartikel.
          </p>
        </div>

        <div className="rz-article-automation-controls">
          <label className="rz-article-automation-field">
            <span className="rz-article-automation-label">Automatische afboeking bij aankoop</span>
            <select
              className="rz-article-automation-select"
              value={mode}
              onChange={handleChange}
              disabled={!consumable}
            >
              <option value={AUTO_CONSUME_MODES.FOLLOW_HOUSEHOLD}>Huishoudinstelling volgen</option>
              <option value={AUTO_CONSUME_MODES.NONE}>Geen automatische afboeking</option>
              <option value={AUTO_CONSUME_MODES.CONSUME_PURCHASED_QUANTITY}>Boek hetzelfde aantal af als gekocht</option>
              <option value={AUTO_CONSUME_MODES.CONSUME_ALL_EXISTING}>Boek bestaande voorraad eerst volledig af tot 0</option>
            </select>
          </label>

          <div className="rz-article-automation-helper-row">
            <span className="rz-article-automation-helper">
              {consumable ? 'Alleen van toepassing op verbruiksartikelen.' : 'Alleen relevant voor verbruiksartikelen.'}
            </span>
            {saveMessage ? (
              <span className="rz-inline-feedback rz-inline-feedback--success rz-article-automation-feedback">{saveMessage}</span>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  )
}

export default function ArticleOverviewTab({ articleData = {}, visibilityMap = {}, visibilityLoading = false, visibilityError = null }) {
  const groupedFields = useMemo(() => getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW), [])
  const overviewVisibility = visibilityMap?.overview || {}

  const visibleGroups = useMemo(() => {
    return Object.entries(groupedFields).reduce((acc, [groupKey, fields]) => {
      const visible = fields.filter((field) => overviewVisibility[field.key] === true)
      if (visible.length > 0) acc[groupKey] = visible
      return acc
    }, {})
  }, [groupedFields, overviewVisibility])

  if (visibilityLoading) {
    return <div className="rz-empty-state">Overzichtsvelden worden geladen.</div>
  }

  if (Object.keys(visibleGroups).length === 0) {
    return <div className="rz-empty-state">Er zijn geen zichtbare velden ingesteld voor Overzicht.</div>
  }

  return (
    <div className="rz-overview-tab">
      {visibilityError ? <div className="rz-article-detail-alert">Veldinstellingen konden niet volledig worden geladen. Standaardvelden worden getoond.</div> : null}
      <AutomationOverrideCard articleData={articleData} />
      {Object.entries(visibleGroups).map(([groupKey, fields]) => (
        <section key={groupKey} className="rz-overview-group rz-article-detail-section">
          <h3 className="rz-overview-group-title rz-article-detail-section-title">{GROUP_LABELS[groupKey] || groupKey}</h3>
          <div className="rz-overview-group-body rz-article-detail-section-body">
            {fields.map((field) => (
              <FieldRow key={field.key} label={field.label} value={resolveArticleFieldValue(field.key, articleData)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
