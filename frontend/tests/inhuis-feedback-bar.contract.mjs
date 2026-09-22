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
const mobileArticleSource = readFrontend('src/features/articles/MobileArticlePage.jsx')
const mobileArticleCss = readFrontend('src/features/articles/mobileArticleDetail.css')
const mobileInventorySource = readFrontend('src/pages/MobileVoorraad.jsx')
const mobileInventoryCss = readFrontend('src/pages/mobileVoorraad.css')

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
// The migrated mobile Voorraad root has its own fixed bottom navigation.
// It no longer reserves or offsets a sticky CTA above the legacy permanent feedback bar.
assert.doesNotMatch(mobileInventorySource, /className="rz-mobile-inventory-actions"/)
assert.match(
  mobileInventorySource,
  /className="rz-mobile-inventory-summary-row"[\s\S]*data-testid="mobile-inventory-add-incidental-purchase"/,
)
assert.match(mobileInventorySource, /data-testid="mobile-inventory-bottom-nav"/)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-content\s*\{[\s\S]*padding:\s*12px 14px calc\(86px \+ env\(safe-area-inset-bottom\)\);/,
)
assert.match(
  mobileInventoryCss,
  /\.rz-mobile-inventory-bottom-nav\s*\{[\s\S]*position:\s*fixed;[\s\S]*bottom:\s*0;/,
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
assert.match(themeCss, /\.rz-mobile-article-feedback[\s\S]*position:\s*fixed\s*!important;[\s\S]*bottom:\s*0;[\s\S]*height:\s*var\(--size-app-bar-mobile\)/)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\) \.rz-app-feedback-bar-base,[\s\S]*\[data-testid="app-feedback-bar-scroll-clearance"\][\s\S]*display:\s*none\s*!important;/,
)
assert.match(
  themeCss,
  /body:has\(\[data-testid="mobile-inventory-page"\]\)[\s\S]*\[data-testid\^="app-feedback-"\][\s\S]*inset:\s*auto 0 calc\(60px \+ env\(safe-area-inset-bottom\)\) 0\s*!important;/,
)

assert.match(mobileArticleCss, /\.rz-mobile-article-detail-row\s*\{[\s\S]*padding:\s*9px var\(--space-mobile-field-inline\);/)
assert.match(mobileArticleCss, /\.rz-mobile-article-action-row\s*\{[\s\S]*padding:\s*10px var\(--space-mobile-field-inline\);/)
assert.match(mobileArticleCss, /\.rz-mobile-article-inline-panel\s*\{[\s\S]*padding:\s*10px var\(--space-mobile-field-inline\) 12px;/)
assert.match(mobileArticleCss, /\.rz-mobile-article-history-row\s*\{[\s\S]*padding:\s*0 var\(--space-mobile-field-inline\);/)

assert.match(providerSource, /data-testid=\{`\$\{testId\}-overlay`\}/)
assert.match(providerSource, /data-testid=\{`\$\{testId\}-ok-button`\}/)
assert.match(providerSource, /data-testid="app-feedback-technical-toggle"/)
assert.match(mobileArticleSource, /rz-mobile-article-feedback/)

console.log('INHUIS_FEEDBACK_BAR_CONTRACT_GREEN')
