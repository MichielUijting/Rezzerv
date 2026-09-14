import { useActionButtonEnabled } from '../features/platform/actionButtonAvailability.js'

export default function Button({ variant = 'primary', className = '', actionKey = null, children, ...props }) {
  const label = typeof children === 'string' ? children.trim() : ''
  const enabled = useActionButtonEnabled({
    actionKey,
    testId: props['data-testid'] || null,
    label,
  })

  if (!enabled) return null

  const cls = [
    variant === 'primary' ? 'rz-button-primary' : 'rz-button-secondary',
    className
  ].filter(Boolean).join(' ')
  return <button className={cls} {...props}>{children}</button>
}
