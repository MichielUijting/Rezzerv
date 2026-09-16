const INHUIS_LOGO_WHITE = "/inhuis-logo-white.png";
const INHUIS_LOGO_HEADER = "/inhuis-logo-header.png";

export default function BrandLogo({ variant = "header" }) {
  const isLogin = variant === "login";
  const cls = isLogin ? "rz-brandlogo-login" : "rz-brandlogo-header";
  const src = isLogin ? INHUIS_LOGO_WHITE : INHUIS_LOGO_HEADER;
  return <img src={src} alt="Inhuis" className={cls} draggable="false" />;
}
