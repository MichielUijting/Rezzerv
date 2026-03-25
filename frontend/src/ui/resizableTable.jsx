import { useEffect, useMemo, useRef, useState } from 'react'

function sumWidths(widths) {
  return Object.values(widths || {}).reduce((sum, value) => sum + Number(value || 0), 0)
}

function buildInitialWidths(defaultWidths, orderedKeys, targetTotal) {
  const next = { ...defaultWidths }
  const keys = orderedKeys.filter((key) => Object.prototype.hasOwnProperty.call(next, key))
  const total = sumWidths(next)
  const lastKey = keys[keys.length - 1]
  if (lastKey && targetTotal > total) {
    next[lastKey] = Math.max(0, Number(next[lastKey] || 0) + Math.round(targetTotal - total))
  }
  return next
}

function normalizeWidths(currentWidths, defaultWidths, orderedKeys, targetTotal, minWidth) {
  const current = { ...currentWidths }
  const keys = orderedKeys.filter((key) => Object.prototype.hasOwnProperty.call(defaultWidths || {}, key))
  if (!keys.length) return { ...defaultWidths }
  keys.forEach((key) => {
    const fallback = Number(defaultWidths?.[key] || 0)
    const currentValue = Number(current?.[key])
    current[key] = Number.isFinite(currentValue) ? Math.max(minWidth, Math.round(currentValue)) : Math.max(minWidth, Math.round(fallback))
  })
  let total = sumWidths(current)
  const lastKey = keys[keys.length - 1]
  if (!lastKey) return current
  if (targetTotal > total) {
    current[lastKey] += Math.round(targetTotal - total)
    return current
  }
  if (targetTotal < total) {
    let remaining = Math.round(total - targetTotal)
    for (let index = keys.length - 1; index >= 0 && remaining > 0; index -= 1) {
      const key = keys[index]
      const available = Math.max(0, current[key] - minWidth)
      if (available <= 0) continue
      const reduction = Math.min(available, remaining)
      current[key] -= reduction
      remaining -= reduction
    }
  }
  return current
}

function rebalanceWidths(currentWidths, orderedKeys, columnKey, desiredWidth, minWidth, targetTotal) {
  const next = { ...currentWidths }
  const keys = orderedKeys.filter((key) => Object.prototype.hasOwnProperty.call(next, key))
  const index = keys.indexOf(columnKey)
  if (index === -1) return next
  const rightKeys = keys.slice(index + 1)
  if (!rightKeys.length) return next

  const startWidth = Math.max(minWidth, Number(next[columnKey] || minWidth))
  const targetWidth = Math.max(minWidth, Math.round(desiredWidth))
  const delta = targetWidth - startWidth
  if (!delta) return next

  if (delta > 0) {
    let remaining = delta
    rightKeys.forEach((key) => {
      if (remaining <= 0) return
      const available = Math.max(0, Number(next[key] || 0) - minWidth)
      if (available <= 0) return
      const reduction = Math.min(available, remaining)
      next[key] = Math.max(minWidth, Number(next[key] || 0) - reduction)
      remaining -= reduction
    })
    next[columnKey] = startWidth + (delta - remaining)
  } else {
    const gain = Math.abs(delta)
    next[columnKey] = targetWidth
    let distributed = 0
    rightKeys.forEach((key, idx) => {
      const share = idx === rightKeys.length - 1 ? gain - distributed : Math.floor(gain / rightKeys.length)
      next[key] = Math.max(minWidth, Math.round(Number(next[key] || 0) + share))
      distributed += share
    })
  }

  return normalizeWidths(next, next, keys, targetTotal, minWidth)
}

export function useResizableColumnWidths(defaultWidths, options = {}) {
  const orderedKeys = useMemo(() => {
    const candidateKeys = Array.isArray(options?.columnOrder) && options.columnOrder.length
      ? options.columnOrder
      : Object.keys(defaultWidths || {})
    return candidateKeys.filter((key) => Object.prototype.hasOwnProperty.call(defaultWidths || {}, key))
  }, [defaultWidths, options?.columnOrder])
  const minWidth = Math.max(40, Number(options?.minWidth || 56))
  const containerRef = options?.containerRef
  const [containerWidth, setContainerWidth] = useState(0)
  const targetTotal = useMemo(() => Math.max(sumWidths(defaultWidths), Math.round(containerWidth || 0)), [defaultWidths, containerWidth])
  const [widths, setWidths] = useState(() => buildInitialWidths(defaultWidths, orderedKeys, targetTotal))
  const widthsRef = useRef(widths)

  useEffect(() => {
    widthsRef.current = widths
  }, [widths])

  useEffect(() => {
    if (!containerRef?.current) return undefined
    const node = containerRef.current
    const update = () => {
      const nextWidth = Math.max(0, Math.round(node.clientWidth || 0))
      setContainerWidth(nextWidth)
    }
    update()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }
    const observer = new ResizeObserver(() => update())
    observer.observe(node)
    return () => observer.disconnect()
  }, [containerRef])

  useEffect(() => {
    setWidths((current) => normalizeWidths(current && Object.keys(current).length ? current : defaultWidths, defaultWidths, orderedKeys, targetTotal, minWidth))
  }, [defaultWidths, orderedKeys, targetTotal, minWidth])

  function startResize(columnKey, event) {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidths = { ...widthsRef.current }
    const startWidth = Number(startWidths?.[columnKey] ?? defaultWidths?.[columnKey] ?? minWidth)

    function handleMouseMove(moveEvent) {
      const delta = moveEvent.clientX - startX
      const nextWidth = Math.max(minWidth, Math.round(startWidth + delta))
      setWidths(rebalanceWidths(startWidths, orderedKeys, columnKey, nextWidth, minWidth, targetTotal))
    }

    function handleMouseUp() {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  return { widths, startResize, tableWidth: buildTableWidth(widths, `${targetTotal || sumWidths(widths)}px`) }
}

export function ResizableHeaderCell({
  columnKey,
  widths,
  onStartResize,
  className = '',
  style = {},
  children,
  sortable = false,
  sortDirection = 'asc',
  isSorted = false,
  onSort = null,
}) {
  return (
    <th className={className} style={{ ...style, position: 'relative', width: widths?.[columnKey] ? `${widths[columnKey]}px` : style.width }}>
      {sortable ? (
        <button
          type="button"
          className="rz-sort-button"
          onClick={() => onSort?.(columnKey)}
          aria-pressed={isSorted}
          aria-label={`${typeof children === 'string' ? children : 'Kolom'} sorteren`}
        >
          <span>{children}</span>
          <span className={`rz-sort-indicator${isSorted ? ' is-active' : ''}`} data-direction={isSorted ? sortDirection : 'desc'} aria-hidden="true" />
        </button>
      ) : (
        <div style={{ paddingRight: '10px' }}>{children}</div>
      )}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Kolom breedte aanpassen"
        onMouseDown={(event) => onStartResize(columnKey, event)}
        style={{
          position: 'absolute',
          top: 0,
          right: '-3px',
          width: '8px',
          height: '100%',
          cursor: 'col-resize',
          userSelect: 'none',
          touchAction: 'none',
          zIndex: 2,
        }}
      />
    </th>
  )
}

export function buildTableWidth(widths, fallbackWidth = '100%') {
  const total = sumWidths(widths)
  return total > 0 ? `max(${total}px, ${fallbackWidth})` : fallbackWidth
}
