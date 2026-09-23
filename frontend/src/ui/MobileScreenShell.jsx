import MobileModuleHeader from './MobileModuleHeader.jsx'
import './mobileComponents.css'

export default function MobileScreenShell({
  title,
  testId,
  className = '',
  rootProps = {},
  headerTestId = 'mobile-module-header',
  children,
}) {
  return (
    <div
      className={['rz-screen', 'rz-mobile-screen-shell', className].filter(Boolean).join(' ')}
      data-testid={testId}
      {...rootProps}
    >
      <MobileModuleHeader title={title} testId={headerTestId} />
      {children}
    </div>
  )
}
