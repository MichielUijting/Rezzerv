import { useEffect, useRef, useState } from 'react'

const STORES = [
  { code: 'ah', name: 'Albert Heijn' },
  { code: 'jumbo', name: 'Jumbo' },
  { code: 'lidl', name: 'Lidl' },
]
const TARGET_CLASS = 'rz-receipt-connection-guide-target'
const GUIDE_FINISHED = STORES.length + 1
const storageKey = (householdId) => 'inhuis:onboarding:store-arrows:' + householdId

export function completeStoreConnectionGuidance(householdId) {
  if (!householdId) return
  try { window.localStorage.setItem(storageKey(householdId), String(GUIDE_FINISHED)) } catch {}
}

function readStep(householdId) {
  try {
    const raw = Number(window.localStorage.getItem(storageKey(householdId)))
    return Number.isInteger(raw) && raw >= 0 && raw <= GUIDE_FINISHED ? raw : 0
  } catch {
    return 0
  }
}

/**
 * Pointer-only guidance: never paints/dims the background or intercepts
 * any retailer action. Progress is household-scoped and survives external
 * AH browser handoff; it contains no accounts, receipts or credentials.
 */
export default function StoreConnectionWalkthrough({ householdId, ready, onFinish }) {
  const [step, setStep] = useState(() => readStep(householdId))
  const [position, setPosition] = useState(null)
  const finishedRef = useRef(false)
  const finishRef = useRef(onFinish)
  useEffect(() => { finishRef.current = onFinish }, [onFinish])

  useEffect(() => {
    if (!ready || !householdId || step >= STORES.length) return
    const store = STORES[step]
    const button = document.querySelector('[data-testid="receipt-connection-action-' + store.code + '"]')
    if (!button) return
    button.classList.add(TARGET_CLASS)
    button.setAttribute('data-onboarding-arrow-target', store.code)
    button.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'auto' })

    let frame = null
    function locate() {
      if (!button.isConnected) return
      const rect = button.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const below = rect.top < 150
      const center = rect.left + rect.width / 2
      const left = Math.max(6, Math.min(window.innerWidth - 220, center - 108))
      const top = below ? Math.min(window.innerHeight - 134, rect.bottom + 8) : Math.max(8, rect.top - 133)
      setPosition({ left, top, below })
    }
    function measure() {
      if (frame !== null) cancelAnimationFrame(frame)
      frame = requestAnimationFrame(locate)
    }
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      if (frame !== null) cancelAnimationFrame(frame)
      button.classList.remove(TARGET_CLASS)
      button.removeAttribute('data-onboarding-arrow-target')
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [householdId, ready, step])

  useEffect(() => {
    if (!ready || !householdId || step >= STORES.length) return
    let advanced = false
    function advance() {
      if (advanced) return
      advanced = true
      const next = step + 1
      try { window.localStorage.setItem(storageKey(householdId), String(next)) } catch {}
      setPosition(null)
      setStep(next)
    }
    function keyDown(event) {
      if (event.key === 'ArrowRight') advance()
      if (event.key === 'Escape') {
        try { window.localStorage.setItem(storageKey(householdId), String(STORES.length)) } catch {}
        setStep(STORES.length)
      }
    }
    window.addEventListener('click', advance, true)
    window.addEventListener('keydown', keyDown)
    return () => {
      window.removeEventListener('click', advance, true)
      window.removeEventListener('keydown', keyDown)
    }
  }, [householdId, ready, step])

  useEffect(() => {
    if (!ready || !householdId || step !== STORES.length || finishedRef.current) return
    finishedRef.current = true
    // Let any actual store-button click complete before changing the route.
    const timer = window.setTimeout(() => {
      completeStoreConnectionGuidance(householdId)
      finishRef.current?.()
    }, 250)
    return () => window.clearTimeout(timer)
  }, [householdId, ready, step])

  if (!ready || !householdId || step >= STORES.length || !position) return null

  return (
    <aside
      className={'rz-onboarding-arrow-overlay' + (position.below ? ' rz-onboarding-arrow-overlay--below' : '')}
      data-testid="onboarding-store-arrow"
      data-store={STORES[step].code}
      role="status"
      aria-live="polite"
      style={{ left: position.left, top: position.top }}
    >
      <span className="rz-onboarding-arrow-label" data-testid="onboarding-arrow-step">
        {step + 1}/3 · {STORES[step].name}: tik op de knop
      </span>
      <svg className="rz-onboarding-arrow-shape" viewBox="0 0 116 82" aria-hidden="true">
        <path d="M22 5 C36 23 62 20 62 68" />
        <path d="M43 51 L62 72 L82 52" />
      </svg>
    </aside>
  )
}
