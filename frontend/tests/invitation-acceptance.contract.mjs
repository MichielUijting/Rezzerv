import fs from 'node:fs'

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

const router = read('src/app/router/AppRouter.jsx')
const page = read('src/features/auth/InvitationAcceptancePage.jsx')
const header = read('src/ui/Header.jsx')

const checks = [
  [router.includes("path: '/uitnodiging/:token'"), 'public invitation route exists'],
  [router.includes('InvitationAcceptancePage'), 'public invitation page is wired'],
  [page.includes('/api/household/invitations/accept/'), 'page uses invitation acceptance API'],
  [page.includes('/register'), 'page supports invitation-specific registration'],
  [!page.includes("apiPost('/api/auth/register'"), 'invited registration never calls generic registration'],
  [page.includes('er wordt geen extra leeg huishouden aangemaakt'), 'invited registration copy states no extra household'],
  [page.includes('Inloggen en accepteren'), 'existing-account path is explicit'],
  [header.includes('/api/session/households'), 'header loads authoritative household memberships'],
  [header.includes('/api/session/household'), 'header switches through server session route'],
  [header.includes('data-testid="household-switcher"'), 'household switcher is test-addressable'],
]

for (const [ok, label] of checks) {
  if (!ok) throw new Error(`FAIL ${label}`)
  console.log(`PASS ${label}`)
}

console.log('INVITATION_ACCEPTANCE_FRONTEND_CONTRACT_GREEN')
