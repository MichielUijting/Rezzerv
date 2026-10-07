export default function Button({ variant = 'primary', className = '', children, ...props }) {
  const cls = [
    variant === 'primary' ? 'rz-button-primary' : 'rz-button-secondary',
    className
  ].filter(Boolean).join(' ')
  const isExportAction = typeof children === 'string' && children.trim().toLowerCase() === 'exporteren'
  return (
    <button
      className={cls}
      {...props}
      data-mobile-export-action={isExportAction ? 'true' : undefined}
    >
      {children}
    </button>
  )
}
