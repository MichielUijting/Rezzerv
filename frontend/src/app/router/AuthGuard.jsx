import { Navigate } from "react-router-dom";

export default function AuthGuard({ children }) {
  const token = localStorage.getItem("rezzerv_token");
  return token ? children : <Navigate to="/login" replace />;
}
