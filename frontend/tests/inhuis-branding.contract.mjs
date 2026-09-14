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

assert.match(brandLogo, /className="rz-brandlogo-header"/)
assert.match(brandLogo, /className="rz-brandlogo-header-icon"/)
assert.match(brandLogo, /className="rz-brandlogo-header-name">Inhuis<\/span>/)
assert.match(brandLogo, /stroke="currentColor"/)
assert.match(brandLogo, /aria-label="Inhuis"/)
assert.doesNotMatch(brandLogo, /REZZERV_LOGO_WHITE/)

assert.match(headerCss, /\.rz-header-logo[\s\S]*margin-left:\s*auto/)
assert.match(headerCss, /\.rz-header-logo[\s\S]*align-items:\s*center/)
assert.match(headerCss, /\.rz-header-logo[\s\S]*justify-content:\s*flex-end/)
assert.match(headerCss, /\.rz-brandlogo-header[\s\S]*color:\s*#FFFFFF/i)
assert.match(headerCss, /\.rz-brandlogo-header[\s\S]*align-items:\s*center/)
assert.match(headerCss, /\.rz-brandlogo-header-name[\s\S]*color:\s*#FFFFFF/i)

assert.match(indexHtml, /<title>Inhuis<\/title>/)
assert.equal(manifest.name, 'Inhuis')
assert.equal(manifest.short_name, 'Inhuis')
assert.equal(manifest.description, 'Inhuis kassabon-inname en voorraadbeheer')
assert.equal(manifest.icons?.[0]?.src, '/inhuis-app-icon.png')
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-white.png')))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-app-icon.png')))

console.log('INHUIS_BRANDING_CONTRACT_GREEN')
