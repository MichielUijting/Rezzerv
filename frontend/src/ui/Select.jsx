import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './components/select.css'

const SELECT_MAX_VISIBLE_OPTIONS = 5
const SELECT_OPTION_HEIGHT = 44
const SELECT_LISTBOX_VERTICAL_PADDING = 8
const SELECT_LISTBOX_MAX_HEIGHT = (SELECT_MAX_VISIBLE_OPTIONS * SELECT_OPTION_HEIGHT) + SELECT_LISTBOX_VERTICAL_PADDING

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

function getMenuPosition(trigger) {
  if (!trigger || typeof window === 'undefined') return null

  const rect = trigger.getBoundingClientRect()
  const edge = 8
  const gap = 4
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const availableBelow = Math.max(0, viewportHeight - rect.bottom - edge - gap)
  const availableAbove = Math.max(0, rect.top - edge - gap)
  const openAbove = availableBelow < SELECT_LISTBOX_MAX_HEIGHT && availableAbove > availableBelow
  const available = openAbove ? availableAbove : availableBelow
  const width = Math.min(rect.width, Math.max(0, viewportWidth - (edge * 2)))
  const left = Math.min(
    Math.max(edge, rect.left),
    Math.max(edge, viewportWidth - edge - width),
  )
  const maxHeight = Math.max(SELECT_OPTION_HEIGHT, Math.min(SELECT_LISTBOX_MAX_HEIGHT, available))

  if (openAbove) {
    return {
      left: `${left}px`,
      width: `${width}px`,
      bottom: `${Math.max(edge, viewportHeight - rect.top + gap)}px`,
      maxHeight: `${maxHeight}px`,
    }
  }

  return {
    left: `${left}px`,
    width: `${width}px`,
    top: `${Math.min(viewportHeight - edge - 44, rect.bottom + gap)}px`,
    maxHeight: `${maxHeight}px`,
  }
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
  const triggerRef = useRef(null)
  const listboxRef = useRef(null)
  const generatedId = useId()
  const listboxId = `rz-select-${generatedId.replace(/:/g, '')}`
  const normalizedOptions = useMemo(() => normalizeOptions(options), [options])
  const selectedIndex = normalizedOptions.findIndex((option) => option.value === String(value ?? ''))
  const selectedOption = selectedIndex >= 0 ? normalizedOptions[selectedIndex] : normalizedOptions[0]
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(selectedIndex >= 0 ? selectedIndex : 0)
  const [menuPosition, setMenuPosition] = useState(null)

  useEffect(() => {
    if (!isOpen) return undefined
    const handlePointerDown = (event) => {
      const target = event.target
      if (rootRef.current?.contains(target) || listboxRef.current?.contains(target)) return
      setIsOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : findNextEnabled(normalizedOptions, -1, 1))
  }, [isOpen, selectedIndex, normalizedOptions])

  useLayoutEffect(() => {
    if (!isOpen) {
      setMenuPosition(null)
      return undefined
    }

    const updatePosition = () => setMenuPosition(getMenuPosition(triggerRef.current))
    updatePosition()

    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [isOpen])

  useLayoutEffect(() => {
    if (!isOpen || activeIndex < 0) return
    const activeOption = listboxRef.current?.querySelector(`[data-select-option-index="${activeIndex}"]`)
    activeOption?.scrollIntoView({ block: 'nearest' })
  }, [isOpen, activeIndex])

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

  const listbox = isOpen && menuPosition && typeof document !== 'undefined'
    ? createPortal(
      <div
        ref={listboxRef}
        id={listboxId}
        className="rz-select-listbox"
        role="listbox"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledby}
        aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
        style={menuPosition}
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
            data-select-option-index={index}
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
      </div>,
      document.body,
    )
    : null

  return (
    <div ref={rootRef} className={rootClassName} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
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
      {listbox}
    </div>
  )
}
