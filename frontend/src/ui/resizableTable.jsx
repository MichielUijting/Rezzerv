import { useEffect, useRef, useState } from 'react'

export function useResizableColumnWidths(defaultWidths) {
  const defaultWidthsSignature = Object.entries(defaultWidths || {})
    .map(([key, value]) => `${key}:${Number(value || 0)}`)
    .join('|')
  const [widths, setWidths] = useState(() => ({ ...defaultWidths }))
  const widthsRef = useRef(widths)

  useEffect(() => {
    widthsRef.current = widths
  }, [widths])

  useEffect(() => {
    setWidths({ ...defaultWidths })
  }, [defaultWidthsSignature])

  function startResize(columnKey, event) {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = Number(widthsRef.current?.[columnKey] ?? defaultWidths?.[columnKey] ?? 120)

    function handleMouseMove(moveEvent) {
      const delta = moveEvent.clientX - startX
      const nextWidth = Math.max(56, Math.round(startWidth + delta))
      setWidths((current) => ({ ...current, [columnKey]: nextWidth }))
    }

    function handleMouseUp() {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  return { widths, startResize }
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
  const headerClassName = ['rz-resizable-header-cell', className].filter(Boolean).join(' ')
  const accessibleLabel = typeof children === 'string' ? children : 'Kolom'

  return (
    <th
      className={headerClassName}
      aria-label={sortable ? `${accessibleLabel} sorteren` : accessibleLabel}
      aria-sort={sortable ? (isSorted ? (sortDirection === 'desc' ? 'descending' : 'ascending') : 'none') : undefined}
      style={{ ...style, width: widths?.[columnKey] ? `${widths[columnKey]}px` : style.width }}
    >
      {sortable ? (
        <button
          type="button"
          className="rz-sort-button"
          onClick={() => onSort?.(columnKey)}
          aria-pressed={isSorted}
          aria-label={`${accessibleLabel} sorteren`}
        >
          <span>{children}</span>
          <span className={`rz-sort-indicator${isSorted ? ' is-active' : ''}`} data-direction={isSorted ? sortDirection : 'desc'} aria-hidden="true" />
        </button>
      ) : (
        <div style={{ paddingRight: '14px', textAlign: style?.textAlign || undefined }}>{children}</div>
      )}
      <div
        className="rz-column-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Kolom breedte aanpassen"
        onMouseDown={(event) => onStartResize(columnKey, event)}
        style={{
          position: 'absolute',
          top: 0,
          right: 0,
          width: '12px',
          height: '100%',
          cursor: 'col-resize',
          userSelect: 'none',
          touchAction: 'none',
          zIndex: 4,
        }}
      />
    </th>
  )
}

export function buildTableWidth(widths, fallbackWidth = '100%') {
  const total = Object.values(widths || {}).reduce((sum, value) => sum + Number(value || 0), 0)
  return total > 0 ? `max(${total}px, ${fallbackWidth})` : fallbackWidth
}
