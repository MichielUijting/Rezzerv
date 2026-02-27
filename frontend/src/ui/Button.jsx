export default function Button({ variant = 'primary', fullWidth = false, className = '', ...props }) {
  const cls = [
    'rz-btn',
    variant === 'primary' ? 'rz-btn-primary' : 'rz-btn-secondary',
    fullWidth ? 'rz-btn-full' : '',
    className
  ].filter(Boolean).join(' ')
  return <button className={cls} {...props} />
}
