import { useEffect, useRef } from 'react'

/**
 * One small orange cue over the action bar, only for the first dashboard
 * reached through onboarding. No page tint and no intercepted touch actions.
 */
export default function FirstUseDashboardGuide({ onClose }) {
  const closeRef = useRef(onClose)
  useEffect(() => { closeRef.current = onClose }, [onClose])
  useEffect(() => {
    function dismiss() { closeRef.current?.() }
    function dismissKey(event) { if (event.key === 'Escape') dismiss() }
    window.addEventListener('click', dismiss, true)
    window.addEventListener('keydown', dismissKey)
    return () => {
      window.removeEventListener('click', dismiss, true)
      window.removeEventListener('keydown', dismissKey)
    }
  }, [])

  return (
    <aside className="rz-first-use-action-hint" data-testid="first-use-dashboard-guide"
      role="status" aria-live="polite">
      <strong>Zo gebruik je Inhuis</strong>
      <span>Onderin staan je actieknoppen, zoals Boodschappen, Kassa en Voorraad.
        Via Meer vind je de overige functies. Tik ergens om te beginnen.</span>
      <svg viewBox="0 0 112 54" aria-hidden="true">
        <path d="M14 5 C33 24 58 15 58 40" />
        <path d="M40 26 L58 45 L77 27" />
      </svg>
    </aside>
  )
}
