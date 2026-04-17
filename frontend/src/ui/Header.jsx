import { useLocation } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import "./components/header.css";

export default function Header({ title }) {
  const location = useLocation();

  const email = localStorage.getItem("rezzerv_user_email") || "";
  const household = localStorage.getItem("rezzerv_household_name") || "";

  const showUserBox = location.pathname !== "/login" && email;
  const showHouseholdLine = location.pathname !== "/login" && household;

  return (
    <div className="rz-header" data-testid="app-header">
      <div className="rz-header-left">
        <div className="rz-header-titleblock">
          <div className="rz-header-title">{title}</div>
          {showHouseholdLine && (
            <div className="rz-header-subtitle">Huishouden: {household}</div>
          )}
        </div>
      </div>

      {showUserBox && (
        <div className="rz-userbox-wrapper">
          <div className="rz-userbox">
            <div>{email}</div>
          </div>
        </div>
      )}

      <div className="rz-header-logo">
        <BrandLogo variant="header" />
      </div>
    </div>
  );
}
