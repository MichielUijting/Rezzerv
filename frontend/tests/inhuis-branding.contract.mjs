import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const repoRoot = path.resolve(frontendRoot, '..')

const readFrontend = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
const readRepo = (relativePath) => fs.readFileSync(path.join(repoRoot, relativePath), 'utf8')

const brandLogo = fs.readFileSync(path.join(frontendRoot, 'src/ui/BrandLogo.jsx'), 'utf8')
const headerCss = fs.readFileSync(path.join(frontendRoot, 'src/ui/components/header.css'), 'utf8')
const indexHtml = fs.readFileSync(path.join(frontendRoot, 'index.html'), 'utf8')
const manifest = JSON.parse(fs.readFileSync(path.join(frontendRoot, 'public/manifest.webmanifest'), 'utf8'))

assert.match(brandLogo, /\/inhuis-logo-white\.png/)
assert.match(brandLogo, /alt="Inhuis"/)
assert.doesNotMatch(brandLogo, /REZZERV_LOGO_WHITE/)
assert.match(headerCss, /\.rz-header-logo img[\s\S]*height:\s*44px/)
assert.match(indexHtml, /<title>Inhuis<\/title>/)
assert.equal(manifest.name, 'Inhuis')
assert.equal(manifest.short_name, 'Inhuis')
assert.equal(manifest.description, 'Inhuis kassabon-inname en voorraadbeheer')
assert.equal(manifest.icons?.[0]?.src, '/inhuis-app-icon.png')
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-white.png')))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-app-icon.png')))

// User-visible branding guardrails. Technical REZZERV_* keys, events, storage keys,
// provider/class names and test credentials may intentionally remain Rezzerv internally.
const loginPage = readFrontend('src/features/auth/LoginPage.jsx')
const kassaPage = readFrontend('src/features/receipts/KassaPage.jsx')
const shareIcon = readFrontend('public/rezzerv-share-icon.svg')

assert.doesNotMatch(loginPage, /admin@rezzerv\.local/)
assert.doesNotMatch(loginPage, /Rezzerv123/)
assert.match(loginPage, /placeholder="naam@voorbeeld\.nl"/)
assert.match(shareIcon, /aria-label="Inhuis"/)
assert.doesNotMatch(kassaPage, /aria-label="[^"]*Rezzerv/)

// PR253 deliberately executes this frontend contract in a frontend-only container.
// Keep frontend branding mandatory there; additionally prove backend branding whenever
// the full repository is available (local/full-repo CI) instead of requiring absent mounts.
const fullRepoBrandingAvailable = fs.existsSync(path.join(repoRoot, 'backend/app/main.py'))
if (fullRepoBrandingAvailable) {
  const emailConfig = readRepo('backend/app/services/email_config_service.py')
  const backendMain = readRepo('backend/app/main.py')
  const superuserRoutes = readRepo('backend/app/api/superuser_routes.py')
  const superuserHouseholdRoutes = readRepo('backend/app/api/superuser_household_routes.py')
  const inboundGuard = readRepo('backend/app/services/receipt_resend_inbound_source_household_guard.py')
  const legacyScanner = readRepo('backend/app/integrations/receipt_scanners/adapters/rezzerv_legacy.py')
  const supportRoutes = readRepo('backend/app/api/support_message_routes.py')
  const compose = readRepo('docker-compose.yml')

  assert.match(emailConfig, /REZZERV_GMAIL_LABEL_NAME', 'Inhuis\/Bonnen'/)
  assert.match(emailConfig, /REZZERV_NOTIFICATION_FROM_NAME', 'Inhuis'/)
  assert.doesNotMatch(emailConfig, /'Rezzerv\/Bonnen'/)
  assert.match(compose, /REZZERV_NOTIFICATION_FROM_NAME:\s*Inhuis/)

  assert.match(backendMain, /Je bent uitgenodigd voor Inhuis als/)
  assert.match(backendMain, /<title>Inhuis Gmail koppeling<\/title>/)
  assert.match(backendMain, /Gmail is gekoppeld aan Inhuis\./)
  assert.doesNotMatch(backendMain, /Je bent uitgenodigd voor Rezzerv als/)
  assert.doesNotMatch(backendMain, /<title>Rezzerv Gmail koppeling<\/title>/)
  assert.doesNotMatch(backendMain, /Gmail is gekoppeld aan Rezzerv\./)

  assert.match(superuserRoutes, /Inhuis Beheercentrum/)
  assert.doesNotMatch(superuserRoutes, /Rezzerv Beheercentrum/)
  assert.match(superuserHouseholdRoutes, /Onbekend read-only Inhuis-scherm/)
  assert.match(inboundGuard, /Inhuis-ontvangstadres/)
  assert.match(inboundGuard, /actief Inhuis-adres/)
  assert.match(legacyScanner, /Inhuis kassabonscanner/)
  assert.match(supportRoutes, /Inhuis-gebruiker/)
}

console.log('INHUIS_BRANDING_CONTRACT_GREEN')
