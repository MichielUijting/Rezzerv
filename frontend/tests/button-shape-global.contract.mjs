import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const theme = readFileSync(new URL('../src/ui/theme.css', import.meta.url), 'utf8')
const tokens = readFileSync(new URL('../src/ui/tokens.css', import.meta.url), 'utf8')

assert.match(tokens, /--radius-md:\s*6px;/, 'centrale knopradius moet 6px blijven')
assert.match(
  theme,
  /button,\s*a\[role="button"\]\s*\{\s*border-radius:\s*var\(--radius-md\)\s*!important;/s,
  'theme.css moet de app-brede knopvorm afdwingen',
)

const root = new URL('../src/', import.meta.url)
const offenders = []
function scan(directoryUrl) {
  for (const entry of readdirSync(directoryUrl, { withFileTypes: true })) {
    const url = new URL(entry.name + (entry.isDirectory() ? '/' : ''), directoryUrl)
    if (entry.isDirectory()) scan(url)
    else if (entry.name.endsWith('.css')) {
      const css = readFileSync(url, 'utf8')
      for (const match of css.matchAll(/([^{}]*button[^{}]*)\{([^{}]*)\}/gi)) {
        const radius = match[2].match(/border-radius\s*:\s*([^;}]+)/i)
        if (radius && /999px|50%/.test(radius[1])) offenders.push(url.pathname + ' :: ' + match[1].trim() + ' => ' + radius[1].trim())
      }
    }
  }
}
scan(root)
assert.deepEqual(offenders, [], 'pil-/cirkelvormige button CSS is niet toegestaan; gebruik de centrale knopvorm:\n' + offenders.join('\n'))
console.log('BUTTON_SHAPE_GLOBAL_GREEN')
