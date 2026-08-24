import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import BrandLogo from "./BrandLogo.jsx";
import { fetchAuthContext, readStoredAuthContext } from "../lib/authSession.js";
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
  const [households, setHouseholds] = useState([]);
  const [switching, setSwitching] = useState(false);

  const email = String(authContext?.email || authContext?.user_id || "").trim();
  const household = activeHouseholdLabel(authContext);
  const activeHouseholdId = String(authContext?.active_household_id || "").trim();

  const showUserBox = location.pathname !== "/login" && Boolean(email);
  const showHouseholdLine = location.pathname !== "/login" && Boolean(household);

  useEffect(() => {
    let cancelled = false;
    async function loadHouseholds() {
      if (!email || authContext?.context_type !== "regular") {
        setHouseholds([]);
        return;
      }
      try {
        const response = await fetch("/api/session/households", {
          method: "GET",
          credentials: "include",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });
        if (!response.ok) return;
        const data = await response.json().catch(() => ({}));
        if (!cancelled) setHouseholds(Array.isArray(data?.items) ? data.items : []);
      } catch {}
    }
    loadHouseholds();
    return () => { cancelled = true; };
  }, [email, authContext?.context_type, activeHouseholdId]);

  async function switchHousehold(event) {
    const nextHouseholdId = String(event.target.value || "").trim();
    if (!nextHouseholdId || nextHouseholdId === activeHouseholdId || switching) return;
    setSwitching(true);
    try {
      const response = await fetch("/api/session/household", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ household_id: nextHouseholdId }),
        cache: "no-store",
      });
      if (!response.ok) return;
      await fetchAuthContext({ force: true });
      window.location.assign("/home");
    } finally {
      setSwitching(false);
    }
  }

  return (
    <div className="rz-header" data-testid="app-header">
      <div className="rz-header-left">
        <div className="rz-header-titleblock">
          <div className="rz-header-title">{title}</div>
          {showHouseholdLine && (
            <div className="rz-header-subtitle">Huishouden: {household}</div>
          )}
          {households.length > 1 && (
            <label className="rz-header-subtitle" style={{ display: "block", marginTop: 4 }}>
              <span className="sr-only">Wissel huishouden</span>
              <select
                value={activeHouseholdId}
                onChange={switchHousehold}
                disabled={switching}
                data-testid="household-switcher"
                aria-label="Wissel huishouden"
              >
                {households.map((item) => (
                  <option key={item.household_id} value={item.household_id}>
                    {item.household_name}
                  </option>
                ))}
              </select>
            </label>
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
