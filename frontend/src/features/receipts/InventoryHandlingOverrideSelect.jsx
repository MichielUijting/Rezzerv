import {
  DIRECT_CONSUMPTION,
  STOCK,
  effectiveInventoryHandling,
  inventoryHandlingLabel,
  normalizeInventoryHandlingOverride,
} from './dayArticleHandling'

const DEFAULT_VALUE = ''

export default function InventoryHandlingOverrideSelect({
  articleDefault,
  value = DEFAULT_VALUE,
  disabled = false,
  onChange,
  id,
  'data-testid': dataTestId,
}) {
  const normalizedOverride = normalizeInventoryHandlingOverride(value)
  const effective = effectiveInventoryHandling(articleDefault, normalizedOverride)

  function handleChange(event) {
    const nextValue = normalizeInventoryHandlingOverride(event.target.value)
    onChange?.(nextValue)
  }

  return (
    <select
      id={id}
      className="rz-input rz-store-select"
      value={normalizedOverride || DEFAULT_VALUE}
      disabled={disabled}
      onChange={handleChange}
      data-testid={dataTestId}
      aria-label="Verwerking voor deze bonregel"
      title={`Effectief: ${inventoryHandlingLabel(effective)}`}
    >
      <option value={DEFAULT_VALUE}>
        Standaard: {inventoryHandlingLabel(articleDefault)}
      </option>
      <option value={STOCK}>Opslaan in voorraad</option>
      <option value={DIRECT_CONSUMPTION}>Direct consumeren</option>
    </select>
  )
}
