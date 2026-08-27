import Card from '../../ui/Card.jsx'

const optionStyle = (checked, disabled) => ({
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  padding: '10px 12px',
  border: checked ? '2px solid currentColor' : '1px solid currentColor',
  borderRadius: 8,
  opacity: disabled ? 0.55 : 1,
  cursor: disabled ? 'not-allowed' : 'pointer',
})

export function RadioChoices({
  name,
  value,
  onChange,
  options,
  disabled = false,
  testId = 'onboarding-radio',
}) {
  return (
    <div role="radiogroup" aria-label={name} style={{ display: 'grid', gap: 8 }}>
      {options.map((option) => {
        const checked = value === option.value
        return (
          <label key={option.value} style={optionStyle(checked, disabled)}>
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={checked}
              disabled={disabled}
              onChange={() => onChange(option.value)}
              data-testid={option.testId || `${testId}-${option.value}`}
            />
            <span>
              <strong>{option.label}</strong>
              {option.description ? (
                <span style={{ display: 'block', marginTop: 2 }}>{option.description}</span>
              ) : null}
            </span>
          </label>
        )
      })}
    </div>
  )
}

export function BooleanRadioChoices({
  name,
  value,
  onChange,
  yesLabel = 'Ja',
  noLabel = 'Nee',
  yesDescription = '',
  noDescription = '',
  disabled = false,
  testId,
}) {
  return (
    <RadioChoices
      name={name}
      value={value ? 'yes' : 'no'}
      onChange={(nextValue) => onChange(nextValue === 'yes')}
      disabled={disabled}
      testId={testId}
      options={[
        {
          value: 'yes',
          label: yesLabel,
          description: yesDescription,
          testId: `${testId}-yes`,
        },
        {
          value: 'no',
          label: noLabel,
          description: noDescription,
          testId: `${testId}-no`,
        },
      ]}
    />
  )
}

export function CheckboxChoice({
  checked,
  onChange,
  label,
  disabled = false,
  testId,
}) {
  return (
    <label style={optionStyle(checked, disabled)}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        data-testid={testId}
      />
      <span><strong>{label}</strong></span>
    </label>
  )
}

export function ChoiceSummary({ items, title = 'Jouw keuzes' }) {
  const visibleItems = (items || []).filter((item) => item && item.label)
  return (
    <Card>
      <div className="rz-form" data-testid="onboarding-choice-summary">
        <div>
          <h2 style={{ marginTop: 0, marginBottom: 4 }}>{title}</h2>
          <p style={{ marginBottom: 0 }}>
            Je ziet hier direct wat je hebt gekozen. Je kunt een keuze hierboven of hieronder altijd nog aanpassen voordat je verdergaat.
          </p>
        </div>
        <dl style={{ display: 'grid', gridTemplateColumns: 'minmax(150px, 1fr) 2fr', gap: '6px 12px', margin: 0 }}>
          {visibleItems.map((item) => (
            <div key={item.label} style={{ display: 'contents' }}>
              <dt style={{ fontWeight: 700 }}>{item.label}</dt>
              <dd style={{ margin: 0 }}>{item.value || 'Nog niet gekozen'}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Card>
  )
}

export function yesNo(value, yesLabel = 'Ja', noLabel = 'Nee') {
  return value ? yesLabel : noLabel
}
