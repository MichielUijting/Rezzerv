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

assert.match(brandLogo, /\/inhuis-logo-header\.png/)
assert.match(brandLogo, /className="rz-brandlogo-header-image"/)
assert.match(brandLogo, /data-testid="inhuis-header-logo"/)
assert.match(brandLogo, /alt="Inhuis"/)
assert.doesNotMatch(brandLogo, /rz-brandlogo-header-icon/)
assert.doesNotMatch(brandLogo, /<svg/)

assert.match(headerCss, /\.rz-header-logo[\s\S]*margin-left:\s*auto/)
assert.match(headerCss, /\.rz-header-logo[\s\S]*align-items:\s*center/)
assert.match(headerCss, /\.rz-header-logo[\s\S]*justify-content:\s*flex-end/)
assert.match(headerCss, /\.rz-brandlogo-header-image[\s\S]*height:\s*44px/)
assert.match(headerCss, /\.rz-brandlogo-header-image[\s\S]*object-fit:\s*contain/)
assert.match(headerCss, /\.rz-brandlogo-header-image[\s\S]*object-position:\s*right center/)
assert.match(headerCss, /\.rz-brandlogo-header-image[\s\S]*transform:\s*scale\(1\.2\)/)
assert.match(headerCss, /\.rz-brandlogo-header-image[\s\S]*transform-origin:\s*right center/)

assert.match(indexHtml, /<title>Inhuis<\/title>/)
assert.equal(manifest.name, 'Inhuis')
assert.equal(manifest.short_name, 'Inhuis')
assert.equal(manifest.description, 'Inhuis kassabon-inname en voorraadbeheer')
assert.equal(manifest.icons?.[0]?.src, '/inhuis-app-icon.png')
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-header.png')))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-logo-white.png')))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/inhuis-app-icon.png')))

console.log('INHUIS_BRANDING_CONTRACT_GREEN')
