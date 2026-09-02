import fs from 'node:fs'

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

const router = read('src/app/router/AppRouter.jsx')
const login = read('src/features/auth/LoginPage.jsx')
const forgot = read('src/features/auth/ForgotPasswordPage.jsx')
const reset = read('src/features/auth/ResetPasswordPage.jsx')

const checks = [
  [router.includes("path: '/wachtwoord-vergeten'"), 'forgot-password route is public'],
  [router.includes("path: '/wachtwoord-herstellen'"), 'reset-password route is public'],
  [login.includes('data-testid="forgot-password-link"'), 'login exposes recovery entry point'],
  [login.includes('to="/wachtwoord-vergeten"'), 'login links to recovery request'],
  [forgot.includes("/api/auth/password-reset/request"), 'request page uses password-reset request API'],
  [forgot.includes('Als dit e-mailadres bij ons bekend is'), 'request page uses enumeration-safe copy'],
  [reset.includes("window.location.hash"), 'reset token is read from URL fragment'],
  [reset.includes('window.history.replaceState'), 'reset fragment is removed from browser URL'],
  [!reset.includes('localStorage'), 'reset token is never persisted in localStorage'],
  [!reset.includes('sessionStorage'), 'reset token is never persisted in sessionStorage'],
  [reset.includes("/api/auth/password-reset/confirm"), 'reset page uses password-reset confirm API'],
  [reset.includes('new_password: password'), 'new password is posted only on confirmation'],
  [reset.includes('password.length < 10'), 'frontend enforces minimum password length'],
  [reset.includes('password.length > 256'), 'frontend enforces maximum password length'],
  [reset.includes('Inloggen met nieuw wachtwoord'), 'successful reset requires explicit login'],
  [!reset.includes('fetchAuthContext'), 'successful reset does not auto-login'],
]

for (const [ok, label] of checks) {
  if (!ok) throw new Error(`FAIL ${label}`)
  console.log(`PASS ${label}`)
}

console.log('PASSWORD_RECOVERY_FRONTEND_CONTRACT_GREEN')
