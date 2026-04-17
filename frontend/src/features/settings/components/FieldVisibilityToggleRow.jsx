export default function FieldVisibilityToggleRow({
  label,
  checked,
  disabled = false,
  helperText = "",
  onChange,
}) {
  return (
    <label className={`rz-toggle-row ${disabled ? "rz-toggle-row--disabled" : ""}`}>
      <div className="rz-toggle-row-text">
        <span className="rz-toggle-row-label">{label}</span>
        {helperText ? <span className="rz-toggle-row-helper">{helperText}</span> : null}
      </div>

      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="rz-toggle-row-input"
      />
    </label>
  )
}
