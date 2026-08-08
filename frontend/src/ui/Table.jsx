import { useCallback, useRef } from "react"

const DEFAULT_KEYBOARD_STEP = 28
const DEFAULT_PAGE_STEP = DEFAULT_KEYBOARD_STEP * 10
const MIN_RESIZABLE_COLUMN_WIDTH = 56
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
    if (col) col.style.width = `${Math.max(MIN_RESIZABLE_COLUMN_WIDTH, width)}px`
  })

  return colgroup
}

function setTablePixelWidth(table, widths) {
  const totalWidth = widths.reduce((sum, width) => sum + Math.max(MIN_RESIZABLE_COLUMN_WIDTH, width), 0)
  const wrapperWidth = table.parentElement?.clientWidth || 0
  table.style.width = `${Math.max(totalWidth, wrapperWidth)}px`
}

export default function Table({
  wrapperClassName = "",
  tableClassName = "",
  tableStyle = undefined,
  dataTestId = undefined,
  keyboardStep = DEFAULT_KEYBOARD_STEP,
  pageStep = DEFAULT_PAGE_STEP,
  resizableColumns = false,
  children,
}) {
  const resizeRef = useRef(null)

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
    const nextWidths = [...activeResize.widths]
    nextWidths[activeResize.columnIndex] = Math.max(
      MIN_RESIZABLE_COLUMN_WIDTH,
      activeResize.startWidth + delta,
    )

    activeResize.widths = nextWidths
    const col = activeResize.colgroup.children[activeResize.columnIndex]
    if (col) col.style.width = `${nextWidths[activeResize.columnIndex]}px`
    setTablePixelWidth(activeResize.table, nextWidths)
    event.preventDefault()
  }, [])

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
    const nearRightEdge = event.clientX >= rect.right - RESIZE_HIT_ZONE_PX
    if (!nearRightEdge) return

    const columnIndex = columnIndexForHeader(th)
    if (columnIndex < 0) return

    const widths = tableColumnWidths(table)
    const colgroup = ensureResizableColgroup(table, widths)
    setTablePixelWidth(table, widths)

    resizeRef.current = {
      table,
      colgroup,
      columnIndex,
      startX: event.clientX,
      startWidth: widths[columnIndex] || rect.width,
      widths,
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
