import FieldVisibilityToggleRow from './FieldVisibilityToggleRow'

const GROUP_LABELS = {
  basic: 'Basis',
  external: 'Extern',
  nutrition_packaging: 'Voeding & verpakking',
  user: 'Gebruiker',
}

export default function FieldVisibilitySection({ title, tabKey, groupedFields, visibilityMap, alwaysVisibleKeys, onToggle }) {
  return (
    <section style={{ display: 'grid', gap: '12px' }}>
      <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>{title}</h3>
      {Object.entries(groupedFields).map(([groupKey, fields]) => (
        <div key={groupKey} style={{ border: '1px solid #dfe4ea', borderRadius: '12px', padding: '12px 16px' }}>
          <h4 style={{ margin: '0 0 10px 0', fontSize: '15px', fontWeight: 600 }}>{GROUP_LABELS[groupKey] || groupKey}</h4>
          <div>
            {fields.map((field) => (
              <FieldVisibilityToggleRow
                key={field.key}
                label={field.label}
                checked={Boolean(visibilityMap?.[tabKey]?.[field.key])}
                disabled={alwaysVisibleKeys.includes(field.key)}
                helperText={alwaysVisibleKeys.includes(field.key) ? 'Altijd zichtbaar' : ''}
                onChange={() => onToggle(tabKey, field.key)}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}
