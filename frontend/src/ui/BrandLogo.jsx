const INHUIS_LOGIN_LOGO = "/inhuis-logo-white.png";

function InhuisHeaderMark() {
  return (
    <div className="rz-brandlogo-header" role="img" aria-label="Inhuis">
      <svg
        className="rz-brandlogo-header-icon"
        viewBox="0 0 64 64"
        aria-hidden="true"
        focusable="false"
      >
        <path
          d="M9 29.5 29.5 10a3.6 3.6 0 0 1 5 0L55 29.5a5 5 0 0 1 1.5 3.6V49a6 6 0 0 1-6 6h-4M17.5 55h-4a6 6 0 0 1-6-6V33.1A5 5 0 0 1 9 29.5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M19.5 31.5h25l-2.8 16.2a4 4 0 0 1-3.9 3.3H26.2a4 4 0 0 1-3.9-3.3l-2.8-16.2Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M25 31.5c.7-5.8 3.1-9 7-9s6.3 3.2 7 9"
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <path
          d="M27.5 40.5c1.3 2.1 2.8 3.1 4.5 3.1s3.2-1 4.5-3.1"
          fill="none"
          stroke="currentColor"
          strokeWidth="3.4"
          strokeLinecap="round"
        />
      </svg>
      <span className="rz-brandlogo-header-name">Inhuis</span>
    </div>
  );
}

export default function BrandLogo({ variant = "header" }) {
  if (variant === "login") {
    return <img src={INHUIS_LOGIN_LOGO} alt="Inhuis" className="rz-brandlogo-login" />;
  }

  return <InhuisHeaderMark />;
}
