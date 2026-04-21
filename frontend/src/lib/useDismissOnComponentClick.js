import { useEffect } from 'react'

function isInteractiveTarget(target) {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest('button, a, input, select, textarea, label, summary, [role="button"], [role="tab"], [role="checkbox"], [data-testid], .rz-card, .rz-screen-card, .rz-inline-cell-button, .rz-tab'))
}

export default function useDismissOnComponentClick(clearCallbacks = [], enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined

    function handlePointerDown(event) {
      if (!isInteractiveTarget(event.target)) return
      clearCallbacks.forEach((clearCallback) => {
        if (typeof clearCallback === 'function') clearCallback()
      })
    }

    document.addEventListener('pointerdown', handlePointerDown, true)
    return () => document.removeEventListener('pointerdown', handlePointerDown, true)
  }, [enabled, clearCallbacks])
}
