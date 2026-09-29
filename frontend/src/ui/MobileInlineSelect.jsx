import { useRef, useState } from 'react'

/**
 * Expand a real HTML select into an in-page list. Browser popup menus do not
 * reliably inherit the application's font-size preference; size > 1 does.
 * Keeping the list in document flow also avoids clipping by mobile receipt
 * cards, table wrappers and overlay stacking contexts.
 */
export default function MobileInlineSelect({
  value = '',
  options = [],
  onChange,
  disabled = false,
  ariaLabel,
  dataTestId,
}) {
  const [open, setOpen] = useState(false)
  const selectRef = useRef(null)
  const selected = options.find((option) => String(option.value) === String(value))
  const selectedLabel = selected?.label || options[0]?.label || 'Kies...'

  return (
    <div className="rz-mobile-inline-select">
      <button
        type="button"
        className="rz-input rz-mobile-inline-select-trigger"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={`${dataTestId}-options`}
        data-testid={dataTestId}
        onClick={() => {
          if (disabled) return
          setOpen((previous) => !previous)
        }}
      >
        <span>{selectedLabel}</span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && !disabled ? (
        <select
          ref={selectRef}
          id={`${dataTestId}-options`}
          className="rz-mobile-inline-select-options"
          aria-label={ariaLabel}
          size={Math.min(Math.max(options.length, 2), 5)}
          value={String(value)}
          onChange={(event) => {
            const nextValue = event.target.value
            setOpen(false)
            onChange(nextValue)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              setOpen(false)
            }
          }}
        >
          {options.map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  )
}
