import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const repoRoot = path.resolve(frontendRoot, '..')

const readFrontend = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')
const readRepo = (relativePath) => fs.readFileSync(path.join(repoRoot, relativePath), 'utf8')

const brandLogo = readFrontend('src/ui/BrandLogo.jsx')
const headerCss = readFrontend('src/ui/components/header.css')
const tokensCss = readFrontend('src/ui/tokens.css')
const typographyCss = readFrontend('src/ui/typography.css')
const mainSource = readFrontend('src/main.jsx')
const indexHtml = readFrontend('index.html')
const manifest = JSON.parse(readFrontend('public/manifest.webmanifest'))
const tableLoadingOverlay = readFrontend('src/ui/DelayedTableLoadingOverlay.jsx')
const tableLoadingCss = readFrontend('src/ui/tableLoadingOverlay.css')
const externalReceiptOverview = readFrontend('src/features/externalDatabases/ReceiptItemsOverview.jsx')

assert.match(brandLogo, /\/inhuis-logo-header\.png/)
assert.match(brandLogo, /\/inhuis-logo-white\.png/)
assert.doesNotMatch(brandLogo, /data:image\/png;base64,/)
assert.match(brandLogo, /alt="Inhuis"/)
assert.doesNotMatch(brandLogo, /REZZERV_LOGO_WHITE/)
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-header.png')))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-white.png')))
assert.match(headerCss, /\.rz-header-logo img[\s\S]*height:\s*50px/)
assert.match(headerCss, /\.rz-header\s*\{[\s\S]*?background:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /@media \(max-width: 720px\)[\s\S]*?\.rz-header\s*\{[\s\S]*?background:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /background:\s*transparent/)
assert.match(headerCss, /@media \(max-width: 720px\)[\s\S]*\.rz-header-subtitle,[\s\S]*\.rz-userbox-wrapper[\s\S]*display:\s*none/)

assert.match(tokensCss, /--font-family-base:\s*Arial,\s*sans-serif/)
assert.match(tokensCss, /--font-size-ui-body:\s*14px/)
assert.match(tokensCss, /--font-size-ui-title:\s*16px/)
assert.match(typographyCss, /font-family:\s*var\(--font-family-base\)/)
assert.match(typographyCss, /body \*:not\(\[aria-hidden="true"\]\)[\s\S]*font-size:\s*var\(--font-size-ui-body\)\s*!important/)
assert.match(typographyCss, /\[class\*="-title"\][\s\S]*\[data-rz-text-size="title"\][\s\S]*font-size:\s*var\(--font-size-ui-title\)\s*!important/)
assert.match(typographyCss, /button,[\s\S]*input,[\s\S]*select,[\s\S]*textarea,[\s\S]*option[\s\S]*font-family:\s*inherit/)
assert.match(mainSource, /import "\.\/ui\/typography\.css";/)
assert.ok(mainSource.indexOf('./ui/typography.css') > mainSource.indexOf('./ui/base.css'))

assert.match(indexHtml, /<title>Inhuis<\/title>/)
assert.equal(manifest.name, 'Inhuis')
assert.equal(manifest.short_name, 'Inhuis')
assert.equal(manifest.description, 'Inhuis kassabon-inname en voorraadbeheer')
assert.equal(manifest.icons?.[0]?.src, '/inhuis-app-icon.png')
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-app-icon.png')))
assert.match(tableLoadingOverlay, /const DEFAULT_DELAY_MS = 1000/)
assert.match(tableLoadingOverlay, /src="\/inhuis-app-icon\.png"/)
assert.match(tableLoadingOverlay, /data-testid="table-loading-logo"/)
assert.match(tableLoadingCss, /width:\s*min\(250px,\s*70vw\)/)
assert.doesNotMatch(tableLoadingCss, /border-radius:\s*50%/)
assert.match(externalReceiptOverview, /DelayedTableLoadingOverlay active=\{isItemsLoading \|\| isOffLoading\}/)
assert.doesNotMatch(externalReceiptOverview, /showSearchComplete|rz-search-complete-letter|rz-search-progress-indicator/)

// User-visible branding guardrails. Technical REZZERV_* keys, events, storage keys,
// provider/class names and test credentials may intentionally remain Rezzerv internally.
const appSource = readFrontend('src/App.jsx')
const loginPage = readFrontend('src/features/auth/LoginPage.jsx')
const helpAboutPage = readFrontend('src/features/settings/SettingsHelpAboutPage.jsx')
const kassaPage = readFrontend('src/features/receipts/KassaPage.jsx')
const shareIcon = readFrontend('public/rezzerv-share-icon.svg')

assert.doesNotMatch(loginPage, /admin@rezzerv\.local/)
assert.doesNotMatch(loginPage, /Rezzerv123/)
assert.match(loginPage, /placeholder="naam@voorbeeld\.nl"/)
assert.match(loginPage, /data-testid="build-tag"/)
assert.match(loginPage, /formatInhuisVersionLabel\(version\)/)
assert.doesNotMatch(appSource, /data-testid="build-tag"/)
assert.doesNotMatch(helpAboutPage, /help-about-version/)
assert.doesNotMatch(helpAboutPage, /getRezzervVersionTag|formatInhuisVersionLabel/)
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
