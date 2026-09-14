const INHUIS_LOGIN_LOGO = "/inhuis-logo-white.png";
const INHUIS_HEADER_LOGO = "/inhuis-logo-header.png";

export default function BrandLogo({ variant = "header" }) {
  if (variant === "login") {
    return <img src={INHUIS_LOGIN_LOGO} alt="Inhuis" className="rz-brandlogo-login" />;
  }

  return (
    <img
      src={INHUIS_HEADER_LOGO}
      alt="Inhuis"
      className="rz-brandlogo-header-image"
      data-testid="inhuis-header-logo"
    />
  );
}
