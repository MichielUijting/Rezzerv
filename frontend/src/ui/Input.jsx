import "./components/input.css";

export default function Input({ label, fieldClassName = '', ...props }) {
  const wrapperClassName = ['rz-input-field', fieldClassName].filter(Boolean).join(' ')
  return (
    <label className={wrapperClassName}>
      {label && <div className="rz-label">{label}</div>}
      <input className="rz-input" {...props} />
    </label>
  )
}
