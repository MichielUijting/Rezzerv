import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')

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

console.log('INHUIS_BRANDING_CONTRACT_GREEN')
