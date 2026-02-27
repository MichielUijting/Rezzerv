import BrandLogo from './BrandLogo.jsx'

export default function Header({ title }) {
  return (
    <div className="rz-header">
      <div className="rz-header-title">{title}</div>
      <div className="rz-header-logo">
        <BrandLogo variant="header" />
      </div>
    </div>
  )
}
