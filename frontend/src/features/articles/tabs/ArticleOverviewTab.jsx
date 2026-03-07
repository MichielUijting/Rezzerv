import { useMemo } from 'react'
import { getFieldsByTabAndGroup } from '../config/articleFieldHelpers'
import { ARTICLE_TABS } from '../config/articleFieldConstants'
import { resolveArticleFieldValue, EMPTY_VALUE } from '../lib/articleFieldValueResolver'

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

export default function ArticleOverviewTab({ articleData = {}, visibilityMap = {} }) {
  const groupedFields = useMemo(() => getFieldsByTabAndGroup(ARTICLE_TABS.OVERVIEW), [])
  const overviewVisibility = visibilityMap?.overview || {}

  const visibleGroups = useMemo(() => {
    return Object.entries(groupedFields).reduce((acc, [groupKey, fields]) => {
      const visible = fields.filter((field) => overviewVisibility[field.key] === true)
      if (visible.length > 0) acc[groupKey] = visible
      return acc
    }, {})
  }, [groupedFields, overviewVisibility])

  if (Object.keys(visibleGroups).length === 0) {
    return <div className="rz-empty-state">Er zijn geen zichtbare velden ingesteld voor Overzicht.</div>
  }

  return (
    <div className="rz-overview-tab">
      {Object.entries(visibleGroups).map(([groupKey, fields]) => (
        <section key={groupKey} className="rz-overview-group">
          <h3 className="rz-overview-group-title">{GROUP_LABELS[groupKey] || groupKey}</h3>
          <div className="rz-overview-group-body">
            {fields.map((field) => (
              <FieldRow key={field.key} label={field.label} value={resolveArticleFieldValue(field.key, articleData)} />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
