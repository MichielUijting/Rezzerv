import { Link } from 'react-router-dom'
import './mobileComponents.css'

function MobileActionIcon({ type }) {
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
          className="rz-mobile-action-bar-item"
          data-testid={`${testId}-${item.key}`}
          onClick={() => onAction?.(item)}
        >
          <span className="rz-mobile-action-bar-icon"><MobileActionIcon type={item.icon} /></span>
          <span>{item.label}</span>
        </Link>
      ))}
    </nav>
  )
}
