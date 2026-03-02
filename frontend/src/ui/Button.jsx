
export default function Button({ variant = 'primary', className = '', ...props }) {
  const cls = [
    variant === 'primary' ? 'rz-button-primary' : 'rz-button-secondary',
    className
  ].filter(Boolean).join(' ')
  return <button className={cls} {...props} />
}
