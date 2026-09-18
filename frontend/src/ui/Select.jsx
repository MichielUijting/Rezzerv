import { useEffect, useId, useMemo, useRef, useState } from 'react'
import './components/select.css'

function normalizeOptions(options = []) {
  return options.map((option) => ({
    value: String(option?.value ?? ''),
    label: String(option?.label ?? option?.value ?? ''),
    disabled: Boolean(option?.disabled),
  }))
}

function findNextEnabled(options, startIndex, direction) {
  if (!options.length) return -1
  let index = startIndex
  for (let step = 0; step < options.length; step += 1) {
    index = (index + direction + options.length) % options.length
    if (!options[index]?.disabled) return index
  }
  return -1
}

export default function Select({
  value = '',
  onChange,
  options = [],
  className = '',
  triggerClassName = '',
  ariaLabel,
  ariaLabelledby,
  disabled = false,
  dataTestId,
}) {
  const rootRef = useRef(null)
  const generatedId = useId()
  const listboxId = `rz-select-${generatedId.replace(/:/g, '')}`
  const normalizedOptions = useMemo(() => normalizeOptions(options), [options])
  const selectedIndex = normalizedOptions.findIndex((option) => option.value === String(value ?? ''))
  const selectedOption = selectedIndex >= 0 ? normalizedOptions[selectedIndex] : normalizedOptions[0]
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(selectedIndex >= 0 ? selectedIndex : 0)

  useEffect(() => {
    if (!isOpen) return undefined
    const handlePointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) setIsOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : findNextEnabled(normalizedOptions, -1, 1))
  }, [isOpen, selectedIndex, normalizedOptions])

  function openMenu() {
    if (disabled) return
    setIsOpen(true)
  }

  function chooseOption(index) {
    const option = normalizedOptions[index]
    if (!option || option.disabled) return
    onChange?.(option.value)
    setIsOpen(false)
  }

  function handleKeyDown(event) {
    if (disabled) return

    if (event.key === 'Escape') {
      if (isOpen) {
        event.preventDefault()
        setIsOpen(false)
      }
      return
    }

    if (event.key === 'Tab') {
      setIsOpen(false)
      return
    }

    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!isOpen) {
        openMenu()
        return
      }
      const direction = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((current) => findNextEnabled(normalizedOptions, current, direction))
      return
    }

    if (event.key === 'Home' && isOpen) {
      event.preventDefault()
      setActiveIndex(findNextEnabled(normalizedOptions, -1, 1))
      return
    }

    if (event.key === 'End' && isOpen) {
      event.preventDefault()
      setActiveIndex(findNextEnabled(normalizedOptions, 0, -1))
      return
    }

    if ((event.key === 'Enter' || event.key === ' ') && isOpen) {
      event.preventDefault()
      chooseOption(activeIndex)
    }
  }

  const rootClassName = ['rz-select', isOpen ? 'rz-select--open' : '', className].filter(Boolean).join(' ')
  const triggerClasses = ['rz-input', 'rz-select-trigger', triggerClassName].filter(Boolean).join(' ')

  return (
    <div ref={rootRef} className={rootClassName} onKeyDown={handleKeyDown}>
      <button
        type="button"
        className={triggerClasses}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledby}
        data-testid={dataTestId}
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="rz-select-value">{selectedOption?.label || ''}</span>
        <span className="rz-select-caret" aria-hidden="true" />
      </button>

      {isOpen ? (
        <div
          id={listboxId}
          className="rz-select-listbox"
          role="listbox"
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledby}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
        >
          {normalizedOptions.map((option, index) => (
            <button
              key={`${option.value}-${index}`}
              id={`${listboxId}-option-${index}`}
              type="button"
              role="option"
              aria-selected={index === selectedIndex}
              disabled={option.disabled}
              tabIndex={-1}
              className={[
                'rz-select-option',
                index === activeIndex ? 'rz-select-option--active' : '',
                index === selectedIndex ? 'rz-select-option--selected' : '',
              ].filter(Boolean).join(' ')}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => chooseOption(index)}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
