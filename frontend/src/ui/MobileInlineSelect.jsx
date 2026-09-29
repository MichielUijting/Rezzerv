import { useEffect, useRef, useState } from 'react'

/**
 * In-flow listbox: unlike a native <select> popup, its options inherit the
 * application's accessibility font tokens and remain inside the mobile card.
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
  const rootRef = useRef(null)
  const selected = options.find((option) => String(option.value) === String(value))
  useEffect(() => {
    if (!open) return undefined
    function closeOutside(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    function closeEscape(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeEscape)
    }
  }, [open])
  return (
    <div className="rz-mobile-inline-select" ref={rootRef}>
      <button
        type="button"
        className="rz-input rz-mobile-inline-select-trigger"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-haspopup="listbox"
        data-testid={dataTestId}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span>{selected?.label || options[0]?.label || 'Kies...'}</span>
        <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && !disabled ? (
        <div className="rz-mobile-inline-select-options" role="listbox" aria-label={ariaLabel}>
          {options.map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={String(option.value) === String(value)}
              className="rz-mobile-inline-select-option"
              key={String(option.value)}
              onClick={() => {
                setOpen(false)
                onChange(option.value)
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
