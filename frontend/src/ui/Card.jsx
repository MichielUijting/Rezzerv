
export default function Card({ children, className = "" }) {
  return (
    <div className={`rz-card ${className}`.trim()}>
      {children}
    </div>
  );
}
