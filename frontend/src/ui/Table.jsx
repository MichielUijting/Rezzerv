import { useCallback } from "react"

const DEFAULT_KEYBOARD_STEP = 28
const DEFAULT_PAGE_STEP = DEFAULT_KEYBOARD_STEP * 10

export default function Table({
  wrapperClassName = "",
  tableClassName = "",
  tableStyle = undefined,
  dataTestId = undefined,
  keyboardStep = DEFAULT_KEYBOARD_STEP,
  pageStep = DEFAULT_PAGE_STEP,
  children,
}) {
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
  const tableClasses = ["rz-table", tableClassName]
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
      <table className={tableClasses} data-testid={dataTestId} style={tableStyle}>
        {children}
      </table>
    </div>
  )
}
