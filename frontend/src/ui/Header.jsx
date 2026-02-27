export default function Header({ title }) {
  const email = localStorage.getItem("rezzerv_user_email") || "";
  const household = localStorage.getItem("rezzerv_household_name") || "";

  const showBox = email || household;

  return (
    <div className="rz-header">
      <div className="rz-header-title">{title}</div>

      {showBox && (
        <div className="rz-userbox-wrapper">
          <div className="rz-userbox">
            {email && <div>{email}</div>}
            {household && <div>{household}</div>}
          </div>
        </div>
      )}
    </div>
  );
}