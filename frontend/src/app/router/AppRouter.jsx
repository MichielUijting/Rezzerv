import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import LoginPage from "../../features/auth/LoginPage";
import HomePage from "../../features/home/HomePage";
import AuthGuard from "./AuthGuard";

function LoginRoute() {
  const navigate = useNavigate();
  const token = localStorage.getItem("rezzerv_token");

  // PO-keuze: altijd starten op /login, ook als er al een token is.
  function handleLogin(newToken) {
    // login-mechanisme blijft: token in localStorage
    localStorage.setItem("rezzerv_token", newToken);
    navigate("/home", { replace: false });
  }

  return <LoginPage onLoggedIn={handleLogin} />;
}


function ResetSessionRoute() {
  // Robuuste PO-proof reset: wis token(s) en forceer een volledige navigatie naar /login.
  // Dit voorkomt issues met browser history/replace en eventuele strict-mode render-volgorde.
  React.useEffect(() => {
    try {
      localStorage.removeItem("rezzerv_token");
      sessionStorage.clear();
      // Als er ooit extra keys bijkomen, is dit een veilige fallback:
      // localStorage.clear();
    } finally {
      window.location.replace("/login");
    }
  }, []);

  return null;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/reset-session" element={<ResetSessionRoute />} />
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route
          path="/home"
          element={
            <AuthGuard>
              <HomePage />
            </AuthGuard>
          }
        />
        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}