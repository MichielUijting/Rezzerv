import { useLocation } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import { readStoredAuthContext } from "../lib/authSession.js";
import "./components/header.css";

function activeHouseholdLabel(context) {
  const name = String(context?.active_household_name || "").trim();
  if (name) return name;

  const householdId = String(context?.active_household_id ?? "").trim();
  if (householdId === "0") return "Systeemhuishouden";
  return householdId;
}

export default function Header({ title }) {
  const location = useLocation();
  const authContext = readStoredAuthContext();

  const email = String(authContext?.email || authContext?.user_id || "").trim();
  const household = activeHouseholdLabel(authContext);

  const showUserBox = location.pathname !== "/login" && Boolean(email);
  const showHouseholdLine = location.pathname !== "/login" && Boolean(household);

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
