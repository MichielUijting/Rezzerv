import { useLocation, useNavigate } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import { readStoredAuthContext } from "../lib/authSession.js";
import "./components/header.css";

export default function Header({ title }) {
  const location = useLocation();
  const navigate = useNavigate();
  const authContext = readStoredAuthContext();

  const email = String(authContext?.email || authContext?.user_id || "").trim();
  const household = String(authContext?.active_household_name || "").trim();

  const showUserBox = location.pathname !== "/login" && Boolean(email);
  const showHouseholdLine = location.pathname !== "/login" && Boolean(household);
  const showSupportButton = location.pathname !== "/login" && Boolean(email);

  function openSupportComposer() {
    const query = new URLSearchParams({
      new: "1",
      from: `${location.pathname}${location.search || ""}`,
      screen: title || document.title || "Rezzerv",
    });
    navigate(`/meldingen?${query.toString()}`);
  }

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

      <div className="rz-header-right">
        <div className="rz-header-logo">
          <BrandLogo variant="header" />
        </div>
        {showSupportButton && (
          <button
            type="button"
            className="rz-header-support-button"
            onClick={openSupportComposer}
            aria-label="Melding sturen"
            title="Melding sturen"
            data-testid="header-support-button"
          >
            <span aria-hidden="true">✉</span>
          </button>
        )}
      </div>
    </div>
  );
}
