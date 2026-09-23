import { useNavigate } from 'react-router-dom'
import './mobileComponents.css'

function canNavigateBack() {
  if (typeof window === 'undefined') return false
  const historyIndex = Number(window.history?.state?.idx)
  if (Number.isFinite(historyIndex)) return historyIndex > 0
  return Number(window.history?.length || 0) > 1
}

export default function MobileBackButton({
  fallbackRoute = '/home',
  testId = 'mobile-back-button',
}) {
  const navigate = useNavigate()

  function goBack() {
    if (canNavigateBack()) {
      navigate(-1)
      return
    }
    navigate(fallbackRoute)
  }

  return (
    <button
      type="button"
      className="rz-mobile-back-button"
      onClick={goBack}
      data-testid={testId}
      aria-label="Terug"
    >
      Terug
    </button>
  )
}
