import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const manifest = JSON.parse(fs.readFileSync(path.join(frontendRoot, 'public/manifest.webmanifest'), 'utf8'))
const mainSource = fs.readFileSync(path.join(frontendRoot, 'src/main.jsx'), 'utf8')

assert.equal(manifest.name, 'Inhuis')
assert.equal(manifest.short_name, 'Inhuis')
assert.equal(manifest.start_url, '/')
assert.equal(manifest.scope, '/')
assert.equal(manifest.display, 'standalone')
assert.equal(manifest.prefer_related_applications, false)

const icons = Array.isArray(manifest.icons) ? manifest.icons : []
const icon192 = icons.find((icon) => String(icon.sizes || '').split(/\s+/).includes('192x192'))
const icon512 = icons.find((icon) => String(icon.sizes || '').split(/\s+/).includes('512x512'))
assert.ok(icon192, 'manifest must expose a 192x192 install icon')
assert.ok(icon512, 'manifest must expose a 512x512 install icon')
assert.ok(fs.existsSync(path.join(frontendRoot, 'public', icon192.src.replace(/^\//, ''))))
assert.ok(fs.existsSync(path.join(frontendRoot, 'public', icon512.src.replace(/^\//, ''))))
assert.match(mainSource, /serviceWorker\.register\('\/sw\.js'\)/)
assert.ok(fs.existsSync(path.join(frontendRoot, 'public/sw.js')))

console.log('PWA_INSTALLABILITY_CONTRACT_GREEN')
