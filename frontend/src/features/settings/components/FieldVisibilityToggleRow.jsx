export default function FieldVisibilityToggleRow({ label, checked, disabled = false, helperText = '', onChange }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', padding: '8px 0', borderBottom: '1px solid #eef1ef', opacity: disabled ? 0.7 : 1 }}>
      <span>
        <span style={{ display: 'block' }}>{label}</span>
        {helperText ? <span style={{ display: 'block', fontSize: '12px', color: '#667085' }}>{helperText}</span> : null}
      </span>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={onChange} />
    </label>
  )
}
