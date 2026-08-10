function scrollFocusedKassaRowIntoView() {
  const rows = Array.from(document.querySelectorAll('tr[data-testid^="kassa-row-"]'))
  const focused = rows.find((row) => {
    const outline = String(row.style?.outline || '')
    const background = String(row.style?.background || '')
    return outline.includes('2px') || background.includes('ECFDF3') || background.includes('236, 253, 243')
  })
  if (!focused) return
  focused.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
}

export function installKassaInboxFocusRuntime() {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => {}
  let scheduled = false
  const schedule = () => {
    if (scheduled) return
    scheduled = true
    window.requestAnimationFrame(() => {
      scheduled = false
      scrollFocusedKassaRowIntoView()
    })
  }
  const observer = new MutationObserver(schedule)
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['style'],
  })
  schedule()
  return () => observer.disconnect()
}
