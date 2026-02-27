export default function Input({ label, ...props }) {
  return (
    <label>
      <div className="rz-label">{label}</div>
      <input className="rz-input" {...props} />
    </label>
  )
}
