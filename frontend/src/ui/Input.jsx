
import "./components/input.css";

export default function Input({ label, ...props }) {
  return (
    <label>
      {label && <div className="rz-label">{label}</div>}
      <input className="rz-input" {...props} />
    </label>
  )
}
