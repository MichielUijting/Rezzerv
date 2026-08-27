const CHECKBOX_STYLE = {
  accentColor: 'var(--color-brand-primary)',
  width: 18,
  height: 18,
  margin: 0,
}

export default function Checkbox({ style = {}, ...props }) {
  return <input type="checkbox" style={{ ...CHECKBOX_STYLE, ...style }} {...props} />
}
