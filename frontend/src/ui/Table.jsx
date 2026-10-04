import { useCallback, useEffect, useRef } from "react"

const DEFAULT_KEYBOARD_STEP = 28
const DEFAULT_PAGE_STEP = DEFAULT_KEYBOARD_STEP * 10
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
  const wrapperRef = useRef(null)

  useEffect(() => {
    const wrapper = wrapperRef.current
    const table = wrapper?.querySelector('table')
    if (!table) return

    const headers = Array.from(table.querySelectorAll('thead tr:first-child th')).map((cell) =>
      String(cell.textContent || '').trim()
    )
    table.querySelectorAll('tbody tr').forEach((row) => {
      Array.from(row.children).forEach((cell, index) => {
        if (cell.tagName !== 'TD') return
        const label = headers[index] || ''
        if (label) cell.dataset.mobileLabel = label
        else delete cell.dataset.mobileLabel
      })
    })
  }, [children])

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
      <table className={tableClasses} data-testid={dataTestId} style={tableStyle}>
        {children}
      </table>
    </div>
  )
}
