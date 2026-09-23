import MobileAppBottomNavigation from './MobileAppBottomNavigation.jsx'
import MobileBackButton from './MobileBackButton.jsx'
import MobileModuleHeader from './MobileModuleHeader.jsx'
import './mobileComponents.css'

export default function MobileScreenShell({
  title,
  activeKey = '',
  testId,
  className = '',
  rootProps = {},
  headerTestId = 'mobile-module-header',
  backFallbackRoute = '/home',
  children,
}) {
  return (
    <div
      className={['rz-screen', 'rz-mobile-screen-shell', className].filter(Boolean).join(' ')}
      data-testid={testId}
      {...rootProps}
    >
      <MobileModuleHeader title={title} testId={headerTestId} />
      <div className="rz-mobile-screen-back-row">
        <MobileBackButton fallbackRoute={backFallbackRoute} />
      </div>
      {children}
      <MobileAppBottomNavigation activeKey={activeKey} />
    </div>
  )
}
