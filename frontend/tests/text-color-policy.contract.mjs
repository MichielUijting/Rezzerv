import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8')

const policy = read('src/textColorPolicy.css')
const main = read('src/main.jsx')

assert.match(main, /import "\.\/textColorPolicy\.css";/)
assert.match(policy, /--rz-text: #000000/)
assert.match(policy, /--rz-muted: #000000/)
assert.match(policy, /--rz-danger: var\(--color-ui-primary\)/)
assert.match(policy, /span\[style\*='color:'\],[\s\S]*div\[style\*='color:'\][\s\S]*color: #000000 !important/)
assert.match(policy, /a,[\s\S]*\.rz-link,[\s\S]*color: var\(--color-ui-primary\) !important/)
assert.match(policy, /\.rz-header,[\s\S]*\.rz-btn--primary,[\s\S]*color: #ffffff !important/)

console.log('TEXT_COLOR_POLICY_GREEN')
