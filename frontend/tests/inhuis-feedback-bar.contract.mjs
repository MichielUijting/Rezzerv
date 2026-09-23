import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const readFrontend = (relativePath) => fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8')

const tokensCss = readFrontend('src/ui/tokens.css')
const themeCss = readFrontend('src/ui/theme.css')
const feedbackBarCss = readFrontend('src/ui/feedback-bar.css')
const providerSource = readFrontend('src/ui/AppFeedbackProvider.jsx')
const appSource = readFrontend('src/App.jsx')

assert.match(tokensCss, /--size-app-bar:\s*58px/)
assert.match(tokensCss, /--size-app-bar-mobile:\s*64px/)
assert.match(tokensCss, /--space-mobile-field-inline:\s*1ch/)

assert.match(appSource, /import "\.\/ui\/feedback-bar\.css";/)
assert.match(appSource, /className="rz-app-feedback-bar-base"/)
assert.match(appSource, /data-testid="app-feedback-bar-base"/)
assert.match(appSource, /aria-hidden="true"/)
assert.match(appSource, /data-testid="app-feedback-bar-scroll-clearance"/)
assert.match(
  appSource,
  /app-feedback-bar-scroll-clearance[\s\S]*height:\s*'calc\(var\(--size-app-bar-mobile\) \+ env\(safe-area-inset-bottom\)\)'[\s\S]*rz-app-feedback-bar-base/,
)
assert.match(
  feedbackBarCss,
  /\.rz-app-feedback-bar-base\s*\{[\s\S]*position:\s*fixed;[\s\S]*bottom:\s*0;[\s\S]*height:\s*var\(--size-app-bar\);[\s\S]*background:\s*var\(--color-ui-primary\);[\s\S]*pointer-events:\s*none;/,
)
assert.match(
  feedbackBarCss,
  /@media \(max-width: 720px\)[\s\S]*\.rz-app-feedback-bar-base[\s\S]*height:\s*var\(--size-app-bar-mobile\);/,
)
assert.match(
  themeCss,
  /\[data-testid\^="app-feedback-"\]\[data-testid\$="-overlay"\][\s\S]*position:\s*fixed\s*!important;[\s\S]*inset:\s*auto 0 0 0\s*!important;/,
)
assert.match(themeCss, /height:\s*var\(--size-app-bar\)\s*!important/)
assert.match(themeCss, /background:\s*var\(--color-ui-primary\)\s*!important/)
assert.match(themeCss, /color:\s*var\(--color-ui-primary-text\)\s*!important/)
assert.match(themeCss, /:not\(:has\(\[data-testid\$="-primary-button"\]\)\)/)
assert.match(themeCss, /:not\(:has\(\[data-testid\$="-secondary-button"\]\)\)/)
assert.match(themeCss, /:not\(:has\(\.rz-input\)\)/)
assert.match(themeCss, /@media \(max-width: 720px\)[\s\S]*height:\s*var\(--size-app-bar-mobile\)\s*!important/)

console.log('INHUIS_FEEDBACK_BAR_CONTRACT_GREEN')
