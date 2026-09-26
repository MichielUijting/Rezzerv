import { useNavigate } from 'react-router-dom'
import './mobileComponents.css'

export function MobileBackControl({ testId = 'mobile-global-back' }) {
  const navigate = useNavigate()

  function handleBack() {
    const historyIndex = Number(window.history.state?.idx ?? 0)
    if (historyIndex > 0) {
      navigate(-1)
      return
    }
    navigate('/home')
  }

  return (
    <button
      type="button"
      className="rz-mobile-back-control"
      onClick={handleBack}
      data-testid={testId}
      aria-label="Terug"
    >
      Terug
    </button>
  )
}

export default function MobileModuleHeader({ title, testId = 'mobile-module-header', showBack = false, onBack = null, backLabel = 'Terug' }) {
  return (
    <header className="rz-mobile-module-header" data-testid={testId}>
      <div className="rz-mobile-module-header-leading">
        {showBack ? <button type="button" className="rz-mobile-module-header-back" onClick={onBack}>{backLabel}</button> : null}
        <h1>{title}</h1>
      </div>
      <span className="rz-mobile-module-header-wordmark" aria-label="InHuis">
        <span className="rz-mobile-module-header-wordmark-in">In</span>
        <span className="rz-mobile-module-header-wordmark-huis">Huis</span>
      </span>
    </header>
  )
}
