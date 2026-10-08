import { useNavigate } from 'react-router-dom'
import BrandLogo from './BrandLogo.jsx'
import './mobileComponents.css'

export function MobileBackControl({ testId = 'mobile-global-back', onBack = null }) {
  const navigate = useNavigate()

  function handleBack() {
    if (onBack) {
      onBack()
      return
    }
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

export default function MobileModuleHeader({
  title,
  testId = 'mobile-module-header',
  showBack = false,
  onBack = null,
  backLabel = 'Terug',
  backTestId = 'mobile-global-back',
  trailingAction = null,
  className = '',
}) {
  return (
    <header className={`rz-mobile-module-header ${className}`.trim()} data-testid={testId}>
      <div className="rz-mobile-module-header-leading">
        {showBack ? <MobileBackControl testId={backTestId} onBack={onBack} /> : null}
        <h1>{title}</h1>
      </div>
      {trailingAction ? <div className="rz-mobile-module-header-trailing">{trailingAction}</div> : (
        <div className="rz-mobile-module-header-brand"><BrandLogo variant="header" /></div>
      )}
    </header>
  )
}
