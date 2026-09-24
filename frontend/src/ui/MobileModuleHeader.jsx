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

export default function MobileModuleHeader({ title, testId = 'mobile-module-header' }) {
  return (
    <header className="rz-mobile-module-header" data-testid={testId}>
      <div className="rz-mobile-module-header-leading">
        <h1>{title}</h1>
      </div>
      <img
        className="rz-mobile-module-header-logo"
        src="/inhuis-logo-white.png"
        alt="Inhuis"
        draggable="false"
      />
    </header>
  )
}
