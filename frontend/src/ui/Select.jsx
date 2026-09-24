import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './components/select.css'

const MOBILE_SELECT_MEDIA_QUERY = '(max-width: 720px)'
const SELECT_MAX_VISIBLE_OPTIONS = 5
const SELECT_OPTION_HEIGHT = 44
const SELECT_SEARCH_HEIGHT = 44
const SELECT_GAP = 4
const SELECT_POPOVER_PADDING = 8
const SELECT_OPTIONS_MAX_HEIGHT = SELECT_MAX_VISIBLE_OPTIONS * SELECT_OPTION_HEIGHT
const SELECT_DESKTOP_POPOVER_MAX_HEIGHT = SELECT_OPTIONS_MAX_HEIGHT + SELECT_POPOVER_PADDING
const SELECT_MOBILE_POPOVER_MAX_HEIGHT = SELECT_DESKTOP_POPOVER_MAX_HEIGHT + SELECT_SEARCH_HEIGHT + SELECT_GAP

function isMobileSelectViewport() {
  return typeof window !== 'undefined' && window.matchMedia(MOBILE_SELECT_MEDIA_QUERY).matches
}

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

function getMenuPosition(trigger, mobileViewport = false) {
  if (!trigger || typeof window === 'undefined') return null

  const rect = trigger.getBoundingClientRect()
  const edge = 8
  const gap = 4
  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const availableBelow = Math.max(0, viewportHeight - rect.bottom - edge - gap)
  const availableAbove = Math.max(0, rect.top - edge - gap)
  const desiredHeight = mobileViewport ? SELECT_MOBILE_POPOVER_MAX_HEIGHT : SELECT_DESKTOP_POPOVER_MAX_HEIGHT
  const openAbove = availableBelow < desiredHeight && availableAbove > availableBelow
  const available = openAbove ? availableAbove : availableBelow
  const width = Math.min(rect.width, Math.max(0, viewportWidth - (edge * 2)))
  const left = Math.min(
    Math.max(edge, rect.left),
    Math.max(edge, viewportWidth - edge - width),
  )
  const maxHeight = Math.max(SELECT_OPTION_HEIGHT + SELECT_POPOVER_PADDING, Math.min(desiredHeight, available))

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
  const popoverRef = useRef(null)
  const listboxRef = useRef(null)
  const searchInputRef = useRef(null)
  const generatedId = useId()
  const listboxId = `rz-select-${generatedId.replace(/:/g, '')}`
  const normalizedOptions = useMemo(() => normalizeOptions(options), [options])
  const selectedIndex = normalizedOptions.findIndex((option) => option.value === String(value ?? ''))
  const selectedOption = selectedIndex >= 0 ? normalizedOptions[selectedIndex] : normalizedOptions[0]
  const [isOpen, setIsOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(selectedIndex >= 0 ? selectedIndex : 0)
  const [menuPosition, setMenuPosition] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [mobileViewport, setMobileViewport] = useState(isMobileSelectViewport)

  const visibleOptions = useMemo(() => {
    const query = searchQuery.trim().toLocaleLowerCase('nl-NL')
    if (!mobileViewport || !query) return normalizedOptions
    return normalizedOptions.filter((option) => option.label.toLocaleLowerCase('nl-NL').includes(query))
  }, [mobileViewport, normalizedOptions, searchQuery])

  const visibleSelectedIndex = visibleOptions.findIndex((option) => option.value === String(value ?? ''))

  useEffect(() => {
    if (!isOpen) return undefined
    const handlePointerDown = (event) => {
      const target = event.target
      if (rootRef.current?.contains(target) || popoverRef.current?.contains(target)) return
      setIsOpen(false)
      setSearchQuery('')
    }
    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [isOpen])

  useEffect(() => {
    const media = window.matchMedia(MOBILE_SELECT_MEDIA_QUERY)
    const updateViewport = () => setMobileViewport(media.matches)
    updateViewport()
    media.addEventListener('change', updateViewport)
    return () => media.removeEventListener('change', updateViewport)
  }, [])

  useEffect(() => {
    if (!isOpen) return
    setActiveIndex(visibleSelectedIndex >= 0 ? visibleSelectedIndex : findNextEnabled(visibleOptions, -1, 1))
  }, [isOpen, visibleOptions, visibleSelectedIndex])

  useLayoutEffect(() => {
    if (!isOpen) {
      setMenuPosition(null)
      return undefined
    }

    const updatePosition = () => setMenuPosition(getMenuPosition(triggerRef.current, mobileViewport))
    updatePosition()

    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [isOpen, mobileViewport])

  useLayoutEffect(() => {
    if (!isOpen || activeIndex < 0) return
    const activeOption = listboxRef.current?.querySelector(`[data-select-option-index="${activeIndex}"]`)
    activeOption?.scrollIntoView({ block: 'nearest' })
  }, [isOpen, activeIndex])

  function openMenu() {
    if (disabled) return
    setSearchQuery('')
    setIsOpen(true)
  }

  function closeMenu() {
    setIsOpen(false)
    setSearchQuery('')
  }

  function chooseOption(index) {
    const option = visibleOptions[index]
    if (!option || option.disabled) return
    onChange?.(option.value)
    closeMenu()
  }

  function handleKeyDown(event) {
    if (disabled) return

    if (event.key === 'Escape') {
      if (isOpen) {
        event.preventDefault()
        closeMenu()
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
      setActiveIndex((current) => findNextEnabled(visibleOptions, current, direction))
      return
    }

    if (event.key === 'Home' && isOpen) {
      event.preventDefault()
      setActiveIndex(findNextEnabled(visibleOptions, -1, 1))
      return
    }

    if (event.key === 'End' && isOpen) {
      event.preventDefault()
      setActiveIndex(findNextEnabled(visibleOptions, 0, -1))
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
        ref={popoverRef}
        className="rz-select-popover"
        style={menuPosition}
        data-testid={dataTestId ? `${dataTestId}-popover` : undefined}
      >
        <label className="rz-select-search">
          <svg className="rz-select-search-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="m16 16 4 4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            ref={searchInputRef}
            type="search"
            className="rz-select-search-input"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault()
                closeMenu()
                triggerRef.current?.focus()
                return
              }
              if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault()
                const direction = event.key === 'ArrowDown' ? 1 : -1
                setActiveIndex((current) => findNextEnabled(visibleOptions, current, direction))
                return
              }
              if (event.key === 'Enter' && activeIndex >= 0) {
                event.preventDefault()
                chooseOption(activeIndex)
              }
            }}
            placeholder="Zoeken…"
            aria-label={ariaLabel ? `Zoek in ${ariaLabel}` : 'Zoek in dropdown'}
            data-testid={dataTestId ? `${dataTestId}-search` : undefined}
          />
        </label>
        <div
          ref={listboxRef}
          id={listboxId}
          className="rz-select-listbox"
          role="listbox"
          aria-label={ariaLabel}
          aria-labelledby={ariaLabelledby}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined}
          data-testid={dataTestId ? `${dataTestId}-listbox` : undefined}
        >
          {visibleOptions.length ? visibleOptions.map((option, index) => (
            <button
              key={`${option.value}-${index}`}
              id={`${listboxId}-option-${index}`}
              type="button"
              role="option"
              aria-selected={option.value === String(value ?? '')}
              disabled={option.disabled}
              tabIndex={-1}
              data-select-option-index={index}
              className={[
                'rz-select-option',
                index === activeIndex ? 'rz-select-option--active' : '',
                option.value === String(value ?? '') ? 'rz-select-option--selected' : '',
              ].filter(Boolean).join(' ')}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => chooseOption(index)}
            >
              {option.label}
            </button>
          )) : (
            <div className="rz-select-empty" role="status">Geen resultaten</div>
          )}
        </div>
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
        onClick={() => {
          if (isOpen) closeMenu()
          else openMenu()
        }}
      >
        <span className="rz-select-value">{selectedOption?.label || ''}</span>
        <span className="rz-select-caret" aria-hidden="true" />
      </button>
      {listbox}
    </div>
  )
}
