const CHECKBOX_STYLE = {
  accentColor: '#1A3E2B',
  width: 18,
  height: 18,
  margin: 0,
}

export default function Checkbox({ style = {}, ...props }) {
  return <input type="checkbox" style={{ ...CHECKBOX_STYLE, ...style }} {...props} />
}
