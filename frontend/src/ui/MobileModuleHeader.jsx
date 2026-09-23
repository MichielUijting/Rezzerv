import './mobileComponents.css'

export default function MobileModuleHeader({ title, testId = 'mobile-module-header' }) {
  return (
    <header className="rz-mobile-module-header" data-testid={testId}>
      <h1>{title}</h1>
      <img
        className="rz-mobile-module-header-logo"
        src="/inhuis-logo-white.png"
        alt="Inhuis"
        draggable="false"
      />
    </header>
  )
}
