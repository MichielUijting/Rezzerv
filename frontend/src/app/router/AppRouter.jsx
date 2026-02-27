import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import LoginPage from "../../features/auth/LoginPage";
import HomePage from "../../features/home/HomePage";
import AuthGuard from "./AuthGuard";

function LoginRoute() {
  const navigate = useNavigate();
  const token = localStorage.getItem("rezzerv_token");

  // Als je al ingelogd bent, ga naar start
  if (token) return <Navigate to="/" replace />;

  function handleLogin(newToken) {
    // login-mechanisme blijft: token in localStorage
    localStorage.setItem("rezzerv_token", newToken);
    navigate("/", { replace: true });
  }

  return <LoginPage onLoggedIn={handleLogin} />;
}


function ResetSessionRoute() {
  const navigate = useNavigate();

  // PO-proof: bezoek /reset-session om de opgeslagen login te wissen
  // en terug te gaan naar het inlogscherm.
  localStorage.removeItem("rezzerv_token");
  return <Navigate to="/login" replace />;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/reset-session" element={<ResetSessionRoute />} />
        <Route
          path="/"
          element={
            <AuthGuard>
              <HomePage />
            </AuthGuard>
          }
        />
        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
