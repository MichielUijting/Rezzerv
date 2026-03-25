import { useEffect, useRef, useState } from 'react'

export function useResizableColumnWidths(defaultWidths) {
  const [widths, setWidths] = useState(() => ({ ...defaultWidths }))
  const widthsRef = useRef(widths)

  useEffect(() => {
    widthsRef.current = widths
  }, [widths])

  useEffect(() => {
    setWidths({ ...defaultWidths })
  }, [defaultWidths])

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
  const total = Object.values(widths || {}).reduce((sum, value) => sum + Number(value || 0), 0)
  return total > 0 ? `${total}px` : fallbackWidth
}
