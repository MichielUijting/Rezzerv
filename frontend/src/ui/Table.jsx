import { useCallback, useEffect, useRef } from "react"
import { MIN_RESIZABLE_COLUMN_WIDTH, resizeTableBoundary } from './tableResize.js'

const DEFAULT_KEYBOARD_STEP = 28
const DEFAULT_PAGE_STEP = DEFAULT_KEYBOARD_STEP * 10
const RESIZE_HIT_ZONE_PX = 8

function columnIndexForHeader(th) {
  const row = th?.parentElement
  if (!row) return -1
  return Array.from(row.children).indexOf(th)
}

function tableColumnWidths(table) {
  return Array.from(table.querySelectorAll('thead tr:first-child th')).map((cell) => Math.round(cell.getBoundingClientRect().width))
}

function ensureResizableColgroup(table, widths) {
  let colgroup = table.querySelector('colgroup')
  if (!colgroup) {
    colgroup = document.createElement('colgroup')
    table.insertBefore(colgroup, table.firstChild)
  }

  while (colgroup.children.length < widths.length) {
    colgroup.appendChild(document.createElement('col'))
  }

  widths.forEach((width, index) => {
    const col = colgroup.children[index]
    if (col) col.style.width = `${Math.max(1, Math.round(Number(width) || 1))}px`
  })

  return colgroup
}

export default function Table({
  wrapperClassName = "",
  tableClassName = "",
  tableStyle = undefined,
  dataTestId = undefined,
  keyboardStep = DEFAULT_KEYBOARD_STEP,
  pageStep = DEFAULT_PAGE_STEP,
  resizableColumns = false,
  onColumnResize = null,
  children,
}) {
  const resizeRef = useRef(null)
  const wrapperRef = useRef(null)

  useEffect(() => {
    const wrapper = wrapperRef.current
    const table = wrapper?.querySelector('table')
    const headerRow = table?.querySelector('thead tr.rz-table-header')
    if (!table || !headerRow || !table.classList.contains('rz-data-table--sticky-filters')) return undefined

    const syncHeaderOffset = () => {
      const height = Math.round(headerRow.getBoundingClientRect().height)
      if (height > 0) table.style.setProperty('--rz-sticky-header-offset', `${height}px`)
    }

    syncHeaderOffset()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(syncHeaderOffset)
    observer.observe(headerRow)
    return () => observer.disconnect()
  }, [children, tableClassName])

  const handleKeyDown = useCallback((event) => {
    const element = event.currentTarget
    if (!element) return

    switch (event.key) {
      case "ArrowDown":
        element.scrollBy({ top: keyboardStep, behavior: "auto" })
        event.preventDefault()
        break
      case "ArrowUp":
        element.scrollBy({ top: -keyboardStep, behavior: "auto" })
        event.preventDefault()
        break
      case "PageDown":
        element.scrollBy({ top: pageStep, behavior: "auto" })
        event.preventDefault()
        break
      case "PageUp":
        element.scrollBy({ top: -pageStep, behavior: "auto" })
        event.preventDefault()
        break
      case "Home":
        element.scrollTo({ top: 0, behavior: "auto" })
        event.preventDefault()
        break
      case "End":
        element.scrollTo({ top: element.scrollHeight, behavior: "auto" })
        event.preventDefault()
        break
      default:
        break
    }
  }, [keyboardStep, pageStep])

  const handleResizeMove = useCallback((event) => {
    const activeResize = resizeRef.current
    if (!activeResize) return

    const delta = event.clientX - activeResize.startX
    const nextWidths = resizeTableBoundary(
      activeResize.startWidths,
      activeResize.columnIndex,
      delta,
      MIN_RESIZABLE_COLUMN_WIDTH,
    )
    const rightColumnIndex = activeResize.columnIndex + 1
    const nextLeftWidth = nextWidths[activeResize.columnIndex]
    const nextRightWidth = nextWidths[rightColumnIndex]

    const leftCol = activeResize.colgroup.children[activeResize.columnIndex]
    const rightCol = activeResize.colgroup.children[rightColumnIndex]
    if (leftCol) leftCol.style.width = `${nextLeftWidth}px`
    if (rightCol) rightCol.style.width = `${nextRightWidth}px`

    onColumnResize?.(activeResize.columnIndex, nextLeftWidth)
    onColumnResize?.(rightColumnIndex, nextRightWidth)
    event.preventDefault()
  }, [onColumnResize])

  const handleResizeEnd = useCallback(() => {
    if (!resizeRef.current) return
    document.removeEventListener('mousemove', handleResizeMove)
    document.removeEventListener('mouseup', handleResizeEnd)
    document.body.classList.remove('rz-table-column-resizing')
    resizeRef.current = null
  }, [handleResizeMove])

  const handleMouseDown = useCallback((event) => {
    if (!resizableColumns || event.button !== 0) return

    const th = event.target?.closest?.('th')
    const table = event.currentTarget
    if (!th || !table.contains(th)) return

    const rect = th.getBoundingClientRect()
    const headerColumnIndex = columnIndexForHeader(th)
    if (headerColumnIndex < 0) return

    const nearLeftEdge = event.clientX <= rect.left + RESIZE_HIT_ZONE_PX
    const nearRightEdge = event.clientX >= rect.right - RESIZE_HIT_ZONE_PX
    let columnIndex = headerColumnIndex

    if (nearLeftEdge && headerColumnIndex > 0) {
      columnIndex = headerColumnIndex - 1
    } else if (!nearRightEdge) {
      return
    }

    const widths = tableColumnWidths(table)
    if (columnIndex < 0 || columnIndex >= widths.length - 1) return

    const fixedTableWidth = Math.round(table.getBoundingClientRect().width)
    const colgroup = ensureResizableColgroup(table, widths)
    table.style.width = `${fixedTableWidth}px`

    resizeRef.current = {
      table,
      colgroup,
      columnIndex,
      startX: event.clientX,
      startWidths: widths,
    }

    document.body.classList.add('rz-table-column-resizing')
    document.addEventListener('mousemove', handleResizeMove)
    document.addEventListener('mouseup', handleResizeEnd)
    event.preventDefault()
    event.stopPropagation()
  }, [handleResizeEnd, handleResizeMove, resizableColumns])

  const wrapperClasses = ["rz-table-component", "rz-table-wrapper", wrapperClassName]
    .filter(Boolean)
    .join(" ")
  const tableClasses = ["rz-table", resizableColumns ? "rz-table--resizable-columns" : "", tableClassName]
    .filter(Boolean)
    .join(" ")

  return (
    <div
      ref={wrapperRef}
      className={wrapperClasses}
      tabIndex={0}
      role="region"
      aria-label="Tabel"
      onKeyDown={handleKeyDown}
      data-row-limit="10"
    >
      <table className={tableClasses} data-testid={dataTestId} style={tableStyle} onMouseDown={handleMouseDown}>
        {children}
      </table>
    </div>
  )
}
