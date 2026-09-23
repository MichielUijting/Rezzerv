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
const legacyStylesCss = readFrontend('src/styles.css')
const mainSource = readFrontend('src/main.jsx')

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
assert.match(themeCss, /\.rz-table thead tr\.rz-table-header th,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-table-header \.rz-sort-button,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)

assert.match(mainSource, /import "\.\/ui\/theme\.css";/)
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
]
const sourceExtensions = new Set(['.css', '.js', '.jsx', '.ts', '.tsx'])
function listSourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name)
    if (entry.isDirectory()) return listSourceFiles(entryPath)
    return sourceExtensions.has(path.extname(entry.name).toLowerCase()) ? [entryPath] : []
  })
}
const primaryColorViolations = []
for (const filePath of listSourceFiles(path.join(frontendRoot, 'src'))) {
  const content = fs.readFileSync(filePath, 'utf8').toUpperCase()
  for (const forbiddenColor of forbiddenPrimaryColors) {
    if (content.includes(forbiddenColor)) {
      primaryColorViolations.push(`${path.relative(frontendRoot, filePath)} bevat oude primaire kleur ${forbiddenColor}`)
    }
  }
}
assert.deepEqual(primaryColorViolations, [], primaryColorViolations.join('\n'))

console.log('INHUIS_PRIMARY_COLOR_CONTRACT_GREEN')
