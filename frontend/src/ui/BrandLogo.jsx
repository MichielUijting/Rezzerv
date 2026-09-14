const INHUIS_LOGO_WHITE = "/inhuis-logo-white.png";

export default function BrandLogo({ variant = "header" }) {
  const cls = variant === "login" ? "rz-brandlogo-login" : "rz-brandlogo-header";
  return <img src={INHUIS_LOGO_WHITE} alt="Inhuis" className={cls} />;
}
