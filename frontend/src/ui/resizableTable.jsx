import { useEffect, useRef, useState } from 'react'

const MIN_RESIZABLE_COLUMN_WIDTH = 56

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

  function setColumnWidth(columnKey, nextWidth) {
    const normalizedWidth = Math.max(
      MIN_RESIZABLE_COLUMN_WIDTH,
      Math.round(Number(nextWidth) || MIN_RESIZABLE_COLUMN_WIDTH),
    )
    setWidths((current) => ({ ...current, [columnKey]: normalizedWidth }))
  }

  function startResize(columnKey, event) {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startWidth = Number(widthsRef.current?.[columnKey] ?? defaultWidths?.[columnKey] ?? 120)

    function handleMouseMove(moveEvent) {
      const delta = moveEvent.clientX - startX
      setColumnWidth(columnKey, startWidth + delta)
    }

    function handleMouseUp() {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  return { widths, startResize, setColumnWidth }
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
      style={style}
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
        style={{
          position: 'absolute',
          top: 0,
          right: '-4px',
          width: '12px',
          height: '100%',
          cursor: 'col-resize',
          userSelect: 'none',
          touchAction: 'none',
          pointerEvents: 'none',
          zIndex: 4,
        }}
      />
    </th>
  )
}

export function buildTableWidth(widths, fallbackWidth = '100%') {
  const total = Object.values(widths || {}).reduce((sum, value) => sum + Number(value || 0), 0)
  return total > 0 ? `${total}px` : fallbackWidth
}
