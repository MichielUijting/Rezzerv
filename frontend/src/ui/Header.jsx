import BrandLogo from './BrandLogo.jsx'

export default function Header({ title }) {
  const email = localStorage.getItem("rezzerv_user_email") || "";
  const household = localStorage.getItem("rezzerv_household_name") || "";

  return (
    <div className="rz-header">
      <div className="rz-header-title">{title}</div>
      <div className="rz-userbox-wrapper">
        {(email || household) && (
          <div className="rz-userbox">
            {email && <div>{email}</div>}
            {household && <div>{household}</div>}
          </div>
        )}
      </div>
    </div>
        <div>{household}</div>
      </div>
      <div className="rz-header-title">{title}</div>
      <div className="rz-header-logo">
        <BrandLogo variant="header" />
      </div>
    </div>
  )
}
