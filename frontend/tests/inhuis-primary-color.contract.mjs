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
const mobileInventoryCss = readFrontend('src/pages/mobileVoorraad.css')
const mobileArticleCss = readFrontend('src/features/articles/mobileArticleDetail.css')
const mainSource = readFrontend('src/main.jsx')
const greenWallpaper = readFrontend('public/inhuis-green-wallpaper.svg')

assert.match(tokensCss, /--color-ui-primary:\s*#28A99E/i)
assert.match(tokensCss, /--color-ui-primary-text:\s*#FFFFFF/i)
assert.match(tokensCss, /--color-brand-primary:\s*#1A3E2B/i)
assert.match(tokensCss, /--space-mobile-field-inline:\s*1ch/i)
assert.match(tokensCss, /--size-app-bar:\s*58px/i)
assert.match(tokensCss, /--size-app-bar-mobile:\s*64px/i)

assert.match(themeCss, /--rz-accent:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /background:\s*var\(--color-ui-primary\)/)
assert.match(headerCss, /color:\s*var\(--color-ui-primary-text\)/)
assert.match(buttonCss, /background:\s*var\(--color-ui-primary\)/)
assert.match(buttonCss, /color:\s*var\(--color-ui-primary-text\)/)
assert.match(legacyStylesCss, /--rz-accent:\s*var\(--color-ui-primary\)/)
assert.match(mobileInventoryCss, /\.rz-mobile-inventory-summary[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(mobileArticleCss, /\.rz-mobile-article-action-row--primary[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-header\s*\{[\s\S]*background:\s*var\(--color-ui-primary\)/)
assert.match(themeCss, /\.rz-header \.rz-header-title,[\s\S]*\.rz-header \.rz-header-subtitle[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-header \.rz-header-logo img[\s\S]*filter:\s*none/)
assert.match(themeCss, /button\.rz-button-primary,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-table thead tr\.rz-table-header th,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-table-header \.rz-sort-button,[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\.rz-mobile-inventory-screen \.rz-mobile-inventory-summary,[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*color:\s*var\(--color-ui-primary-text\)/)
assert.match(themeCss, /\/inhuis-green-wallpaper\.svg/)
assert.match(themeCss, /\.rz-mobile-article-detail-row,[\s\S]*padding-left:\s*var\(--space-mobile-field-inline\)/)
assert.match(greenWallpaper, /lichtgroene gevlekte achtergrond/i)
assert.match(greenWallpaper, /#EEF7F0/i)

assert.match(mainSource, /import "\.\/ui\/theme\.css";/)
assert.ok(mainSource.indexOf('./ui/theme.css') > mainSource.indexOf('./styles.css'))
assert.ok(mainSource.indexOf('./ui/theme.css') > mainSource.indexOf('./ui/typography.css'))

// PO baseline 2026-09-20: primary Inhuis surfaces keep #28A99E and use
// white foreground text/icons application-wide. The exact token pairing is
// the visual contract; accessibility review is handled separately.
assert.match(tokensCss, /--color-ui-primary:\s*#28A99E/i)
assert.match(tokensCss, /--color-ui-primary-text:\s*#FFFFFF/i)

console.log('INHUIS_PRIMARY_COLOR_CONTRACT_GREEN')
