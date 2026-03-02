
import BrandLogo from "./BrandLogo";
import "./components/header.css";

export default function Header({ title, user }) {
  const version = import.meta.env.VITE_REZZERV_VERSION;

  return (
    <header className="app-header">
      <div className="app-header__title">{title}</div>

      <div className="app-header__center">
        {user && (
          <div className="userbox">
            {user.email}
          </div>
        )}
      </div>

      <div className="app-header__logo">
        <BrandLogo />
      </div>

      <div className="app-header__version">
        Rezzerv v{version}
      </div>
    </header>
  );
}
