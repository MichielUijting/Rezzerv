import { cloneElement } from 'react'
import { canCurrentUserPerform } from '../lib/authSession'
import './authorizedControl.css'

export const ADMIN_AUTHORIZATION_MESSAGE = 'Alleen de beheerder is geautoriseerd voor deze functie.'

export default function AuthorizedControl({
  permission,
  children,
  message = ADMIN_AUTHORIZATION_MESSAGE,
  className = '',
  allowed: allowedOverride,
}) {
  const allowed = typeof allowedOverride === 'boolean'
    ? allowedOverride
    : canCurrentUserPerform(permission)

  if (allowed) return children

  const child = cloneElement(children, {
    disabled: 'disabled' in (children.props || {}) ? true : children.props?.disabled,
    'aria-disabled': 'true',
    tabIndex: -1,
    onClick: (event) => {
      event.preventDefault()
      event.stopPropagation()
    },
  })

  return (
    <span
      className={['rz-authorized-control', className].filter(Boolean).join(' ')}
      tabIndex={0}
      role="group"
      aria-label={message}
      data-authorization-message={message}
    >
      {child}
      <span className="rz-authorized-control__tooltip" role="tooltip">{message}</span>
    </span>
  )
}
