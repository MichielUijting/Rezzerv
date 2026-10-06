import { Link } from 'react-router-dom'
import './mobileComponents.css'

function MobileActionIcon({ type, icon }) {
  if (icon) return <span className="rz-mobile-action-bar-desktop-icon" aria-hidden="true">{icon}</span>
  if (type === 'info') {
    return <span className="rz-mobile-action-icon-info" aria-hidden="true">i</span>
  }
  if (type === 'shelf') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 3.5h16v17H4zM4 9h16M4 15h16" />
        <path d="M6 5.5h4v3H6zM13 5.5h5v3h-5zM6 11h6v3H6zM14 11h4v3h-4zM6 17h5v2H6zM13 17h5v2h-5z" />
      </svg>
    )
  }
  if (type === 'register') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 3.5h9v5H6zM5 9h12l2 4v7H4v-7l1-4Z" />
        <path d="M7 12h2M11 12h2M15 12h2M7 15h2M11 15h2M15 15h2M7 18h10" />
      </svg>
    )
  }
  if (type === 'shopping-bag') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 8h12l1 12H5L6 8Z" />
        <path d="M9 8V6a3 3 0 0 1 6 0v2" />
        <path className="rz-bag-stripe rz-bag-stripe--1" d="M6.2 11h11.6" />
        <path className="rz-bag-stripe rz-bag-stripe--2" d="M5.9 14h12.2" />
        <path className="rz-bag-stripe rz-bag-stripe--3" d="M5.7 17h12.6" />
      </svg>
    )
  }
  if (type === 'almost-out') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 5v14h16" />
        <path d="m6 8 4 3 3-2 5 6" />
        <path d="m15 15 3 .2-.2-3" />
      </svg>
    )
  }
  if (type === 'bell') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 10a5 5 0 0 1 10 0v4l1.5 2H5.5L7 14v-4Z" />
        <path d="M10 19h4" />
      </svg>
    )
  }
  if (type === 'inventory') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 7.5 12 4l8 3.5v9L12 20l-8-3.5v-9Z" />
        <path d="m4.5 7.7 7.5 3.4 7.5-3.4M12 11.1V20" />
      </svg>
    )
  }
  if (type === 'clock') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l2.8 1.8" />
      </svg>
    )
  }
  if (type === 'cart') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 5h2l1.5 9h10.8l2-6H6" />
        <circle cx="9" cy="18.5" r="1.2" />
        <circle cx="17" cy="18.5" r="1.2" />
      </svg>
    )
  }
  if (type === 'receipt') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 3h10v18l-2-1.4-2 1.4-2-1.4L9 21l-2-1.4V3Z" />
        <path d="M9.5 8h5M9.5 11h5M9.5 14h3.5" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 7h14M5 12h14M5 17h14" />
    </svg>
  )
}

export default function MobileRecentActionsBar({
  items = [],
  onAction,
  testId = 'mobile-recent-actions',
  ariaLabel = 'Recent gebruikte acties',
}) {
  return (
    <nav
      className="rz-mobile-action-bar"
      aria-label={ariaLabel}
      data-testid={testId}
      style={{ '--rz-mobile-action-count': items.length }}
    >
      {items.map((item) => (
        <Link
          key={item.key}
          to={item.route}
          className={`rz-mobile-action-bar-item${item.showLabel ? '' : ' rz-mobile-action-bar-item--icon-only'}`}
          aria-label={item.label}
          data-testid={`${testId}-${item.key}`}
          onClick={() => onAction?.(item)}
        >
          <span className="rz-mobile-action-bar-icon"><MobileActionIcon type={item.iconType} icon={item.icon} /></span>
          {item.showLabel ? <span>{item.label}</span> : null}
        </Link>
      ))}
    </nav>
  )
}
