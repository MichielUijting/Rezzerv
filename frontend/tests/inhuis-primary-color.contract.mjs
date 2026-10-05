import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const readFrontend = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')

const tokensCss = readFrontend('src/ui/tokens.css')
const themeCss = readFrontend('src/ui/theme.css')
const headerCss = readFrontend('src/ui/components/header.css')
const buttonCss = readFrontend('src/ui/components/button.css')
const searchCandidateCss = readFrontend('src/ui/searchCandidateList.css')
const legacyStylesCss = readFrontend('src/styles.css')
const mainSource = readFrontend('src/main.jsx')
const preferenceSource = readFrontend('src/ui/primaryColorPreference.js')
const settingsSource = readFrontend('src/features/settings/SettingsPage.jsx')
const superuserAppearanceSource = readFrontend('src/features/superuser/SuperuserAppearanceSection.jsx')

assert.match(tokensCss, /--color-ui-primary:\s*#005F6A/i)
assert.match(tokensCss, /--color-ui-primary-text:\s*#FFFFFF/i)
assert.match(tokensCss, /--color-mobile-ui-primary:\s*#005F6A/i)
assert.match(tokensCss, /--color-brand-primary:\s*#005F6A/i)
assert.match(tokensCss, /--space-mobile-field-inline:\s*1ch/i)
assert.match(tokensCss, /--size-app-bar:\s*58px/i)
assert.match(tokensCss, /--size-app-bar-mobile:\s*64px/i)

assert.match(themeCss, /--rz-accent:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /background:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /color:\s*var\(--color-ui-primary-text\)/)
assert.match(buttonCss, /background:\s*var\(--color-ui-primary\)/)
assert.match(buttonCss, /color:\s*var\(--color-ui-primary-text\)/)
assert.match(legacyStylesCss, /--rz-accent:\s*var\(--color-ui-primary\)/)
assert.match(themeCss, /\.rz-header\s*\{[\s\S]*background:\s*var\(--color-ui-primary\)/)
assert.match(themeCss, /\.rz-header \.rz-header-title,[\s\S]*\.rz-header \.rz-header-subtitle[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-header \.rz-header-logo img[\s\S]*filter:\s*none/)
assert.match(themeCss, /button\.rz-button-primary,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(buttonCss, /button\.rz-button-primary:disabled,[\s\S]*background:\s*#d8f3dc;[\s\S]*color:\s*var\(--color-ui-primary\)/i)
assert.match(searchCandidateCss, /\.rz-search-candidate-option--selected[\s\S]*background:\s*var\(--color-brand-light\);[\s\S]*color:\s*var\(--color-brand-primary\)/)
assert.match(themeCss, /\.rz-table thead tr\.rz-table-header th,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-table-header \.rz-sort-button,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)

const textColorPolicyCss = readFrontend('src/textColorPolicy.css')
assert.match(textColorPolicyCss, /\.rz-table thead tr\.rz-table-header th,[\s\S]*\.rz-table thead tr:first-child th,[\s\S]*\.rz-sort-button,[\s\S]*color:\s*#ffffff\s*!important/i)
assert.match(
  textColorPolicyCss,
  /button\.rz-button-primary:disabled,[\s\S]*button\.rz-button-secondary:disabled,[\s\S]*\.rz-search-candidate-option--selected[\s\S]*color:\s*var\(--color-ui-primary\)\s*!important/i,
  'lichtgroene knoppen moeten app-breed donkergroene tekst afdwingen',
)

assert.match(mainSource, /import "\.\/ui\/theme\.css";/)
assert.match(mainSource, /initializePrimaryColorPreference\(\)/)
assert.match(preferenceSource, /DEFAULT_PRIMARY_COLOR\s*=\s*['"]#005F6A['"]/i)
assert.match(preferenceSource, /--color-brand-primary/)
assert.match(preferenceSource, /--color-ui-primary/)
assert.match(preferenceSource, /--color-mobile-ui-primary/)
assert.doesNotMatch(preferenceSource, /localStorage|PRIMARY_COLOR_STORAGE_KEY/i)
assert.match(preferenceSource, /\/api\/platform\/primary-color/)
assert.match(preferenceSource, /contrastWithWhite/)
assert.match(preferenceSource, />=\s*4\.5/)
assert.doesNotMatch(settingsSource, /settings-primary-color-picker|settings-primary-color-hex/)
assert.match(superuserAppearanceSource, /data-testid="superuser-primary-color-picker"/)
assert.match(superuserAppearanceSource, /data-testid="superuser-primary-color-hex"/)
assert.match(superuserAppearanceSource, /\/api\/superuser\/primary-color/)
assert.match(superuserAppearanceSource, /Standaard herstellen/)
assert.ok(mainSource.indexOf('./ui/theme.css') > mainSource.indexOf('./styles.css'))
assert.ok(mainSource.indexOf('./ui/theme.css') > mainSource.indexOf('./ui/typography.css'))

// Global color contract only. Migrated mobile screen visuals are governed by
// mobile-ui-conformity.contract.mjs so legacy mobile baselines cannot block redesigns.
assert.match(tokensCss, /--color-ui-primary:\s*#005F6A/i)
assert.match(tokensCss, /--color-ui-primary-text:\s*#FFFFFF/i)

const forbiddenPrimaryColors = [
  '#1A3E2B',
  '#28A99E',
  '#006B3C',
  '#005630',
  '#0B5D3B',
  '#174F2E',
  '#0F5B32',
  '#146C3A',
  '#285C3A',
  '#176B34',
  '#2E7D4D',
  '#0F5132',
  '#154734',
  '#1F7A3F',
  '#166534',
  '#355247',
  '#1F4D3A',
  '#1D4D3F',
  '#176B35',
  '#0F3D24',
  '#2E7D32',
  '#163020',
]
const sourceExtensions = new Set(['.css', '.js', '.jsx', '.ts', '.tsx', '.svg'])
function listSourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name)
    if (entry.isDirectory()) return listSourceFiles(entryPath)
    return sourceExtensions.has(path.extname(entry.name).toLowerCase()) ? [entryPath] : []
  })
}
const allowedBrandAccentFiles = new Set([
  // Legacy PWA icon assets remain public for existing installed clients/cache compatibility.
  'public/inhuis-app-icon-192.svg',
  'public/inhuis-app-icon-512.svg',
  'public/inhuis-app-icon-brand-192.svg',
  'public/inhuis-app-icon-brand-512.svg',
])
const primaryColorViolations = []
for (const root of ['src', 'public']) {
  for (const filePath of listSourceFiles(path.join(frontendRoot, root))) {
    const relativePath = path.relative(frontendRoot, filePath).replaceAll('\\\\', '/')
    const content = fs.readFileSync(filePath, 'utf8').toUpperCase()
    for (const forbiddenColor of forbiddenPrimaryColors) {
      if (forbiddenColor === '#28A99E' && allowedBrandAccentFiles.has(relativePath)) continue
      if (content.includes(forbiddenColor)) {
        primaryColorViolations.push(`${path.relative(frontendRoot, filePath)} bevat oude primaire kleur ${forbiddenColor}`)
      }
    }
  }
}
assert.deepEqual(primaryColorViolations, [], primaryColorViolations.join('\n'))

const allowedDefaultLiteralFiles = new Set([
  'src/ui/tokens.css',
  'src/ui/primaryColorPreference.js',
  'src/features/admin/lib/browserRegressionRunner.js',
  'public/inhuis-loading-mark.svg',
  'public/rezzerv-share-icon.svg',
  // Legacy PWA icon assets are immutable/cache-facing static brand artwork.
  'public/inhuis-app-icon-192.svg',
  'public/inhuis-app-icon-512.svg',
  'public/inhuis-app-icon-brand-192.svg',
  'public/inhuis-app-icon-brand-512.svg',
])
const hardcodedDefaultViolations = []
for (const root of ['src', 'public']) {
  for (const filePath of listSourceFiles(path.join(frontendRoot, root))) {
    const relativePath = path.relative(frontendRoot, filePath).replaceAll('\\', '/')
    if (allowedDefaultLiteralFiles.has(relativePath)) continue
    const content = fs.readFileSync(filePath, 'utf8').toUpperCase()
    if (content.includes('#005F6A')) {
      hardcodedDefaultViolations.push(`${relativePath} hardcodet #005F6A in plaats van de centrale runtime-token`)
    }
  }
}
assert.deepEqual(hardcodedDefaultViolations, [], hardcodedDefaultViolations.join('\n'))


const lightGreenButtonViolations = []
const lightGreenBackground = /(?:#d8f3dc|#d9f5e0|var\(--color-brand-light\)|var\(--rz-green-light\))/i
const whiteForeground = /color\s*:\s*(?:#fff(?:fff)?|white|var\(--color-ui-primary-text\)|var\(--color-text-inverse\))/i
for (const filePath of listSourceFiles(path.join(frontendRoot, 'src'))) {
  if (path.extname(filePath).toLowerCase() !== '.css') continue
  const relativePath = path.relative(frontendRoot, filePath).replaceAll('\\', '/')
  const css = fs.readFileSync(filePath, 'utf8')
  for (const match of css.matchAll(/([^{}]+)\{([^{}]+)\}/g)) {
    const selector = match[1]
    const declarations = match[2]
    if (!/(button|\.rz-button|\.btn-|candidate-option|action)/i.test(selector)) continue
    if (!lightGreenBackground.test(declarations)) continue
    if (whiteForeground.test(declarations)) {
      lightGreenButtonViolations.push(`${relativePath} :: ${selector.trim()} gebruikt witte tekst op lichtgroen`)
    }
  }
}
assert.deepEqual(
  lightGreenButtonViolations,
  [],
  'Lichtgroene knoppen mogen nergens witte tekst gebruiken:\n' + lightGreenButtonViolations.join('\n'),
)

console.log('INHUIS_PRIMARY_COLOR_CONTRACT_GREEN')
