import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { isTransientFeedback, transientFeedbackDuration } from '../src/ui/feedbackPolicy.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../src')
const provider = fs.readFileSync(path.join(root, 'ui/AppFeedbackProvider.jsx'), 'utf8')

assert.equal(isTransientFeedback({ variant: 'error', dismissMode: 'outside-or-ok' }), false)
assert.equal(isTransientFeedback({ variant: 'error', autoDismissMs: 1000 }), false)
assert.equal(transientFeedbackDuration({ variant: 'error', autoDismissMs: 1000 }), 0)
assert.equal(isTransientFeedback({ variant: 'success' }), true)
assert.match(provider, /dismissMode: variant === 'error' \? 'ok-only'/)
assert.match(provider, /variant !== 'error' && dismissMode === 'outside-or-ok'/)
assert.ok(provider.includes('data-testid={`${testId}-ok-button`}'), 'Elke fout-overlay vereist de centrale OK-knop')
assert.match(provider, /interactiveDialog = variant === 'error'/)
const theme = fs.readFileSync(path.join(root, 'ui/theme.css'), 'utf8')
assert.ok((theme.match(/:not\(:has\(\[data-testid\$="-ok-button"\]\)\)/g) || []).length >= 10,
  'De OK-dialoog mag niet door passieve balk-CSS worden afgedwongen')

const patterns = [
  ['inline-feedback-css', /\brz-inline-feedback\b/g],
  ['inline-alert', /role=['"]alert['"]/g],
  ['inline-status', /role=['"]status['"]/g],
  ['inline-save-status', /data-save-status/g],
  ['native-dialog', /\bwindow\.(?:alert|confirm)\s*\(/g],
  ['page-owned-dismiss', /useDismissOnComponentClick/g],
]
const findings = []
function walk(directory) {
  for (const child of fs.readdirSync(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, child.name)
    if (child.isDirectory()) { walk(absolute); continue }
    if (!/\.(jsx|js)$/.test(child.name) || /\.test\./.test(child.name)) continue
    const relative = path.relative(root, absolute).replaceAll('\\', '/')
    if (relative === 'ui/AppFeedbackProvider.jsx') continue
    const source = fs.readFileSync(absolute, 'utf8')
    for (const [kind, pattern] of patterns) {
      pattern.lastIndex = 0
      for (const match of source.matchAll(pattern)) {
        const line = source.slice(0, match.index).split('\n').length
        findings.push({ file: relative, line, kind })
      }
    }
  }
}
walk(root)

// Previously corrected screens are guarded. Remaining findings constitute an
// actionable legacy inventory, not proof that every match is a notification.
const guardedScreens = [
  'features/settings/SettingsAlmostOutPage.jsx',
  'features/almostOut/AlmostOutPage.jsx',
  'features/almostOut/MobileAlmostOut.jsx',
  'features/articleSynonyms/SynonymAnalysisPage.jsx',
  'features/auth/LoginPage.jsx',
  'features/auth/ForgotPasswordPage.jsx',
  'features/auth/RegisterPage.jsx',
  'features/catalog/CatalogNameEditor.jsx',
  'features/catalog/CatalogBarcodeEntry.jsx',
  'features/articles/tabs/ArticleOverviewTab.jsx',
  'features/catalog/CatalogGpcFrame.jsx',
  'features/externalDatabases/ExternalDatabases2Page.jsx',
  'features/settings/SettingsArticleFieldsPage.jsx',
  'features/settings/SettingsHouseholdAutomationPage.jsx',
  'features/settings/SettingsPrivacyDataSharingPage.jsx',
  'features/settings/SettingsMyAccountPage.jsx',
  'features/settings/SettingsFrontteamPage.jsx',
]
for (const file of guardedScreens) {
  const violations = findings.filter((finding) => finding.file === file
    && ['inline-feedback-css', 'inline-alert', 'inline-save-status', 'page-owned-dismiss'].includes(finding.kind))
  assert.deepEqual(violations, [], `Feedback must use AppFeedbackProvider: ${file}`)
}

const byKind = Object.fromEntries(patterns.map(([kind]) => [
  kind, findings.filter((finding) => finding.kind === kind).length,
]))
const byFile = new Map()
for (const item of findings) {
  if (!byFile.has(item.file)) byFile.set(item.file, new Set())
  byFile.get(item.file).add(item.kind)
}
const inventory = [...byFile].map(([file, kinds]) => ({ file, patterns: [...kinds] }))
  .sort((a, b) => a.file.localeCompare(b.file))

console.log('APP_FEEDBACK_SOURCE_AUDIT_COUNTS=' + JSON.stringify({ files: inventory.length, byKind }))
for (const item of inventory) console.log('APP_FEEDBACK_SOURCE_AUDIT_FILE=' + JSON.stringify(item))
console.log('APP_ERROR_OK_CONFIRMATION_CONTRACT_GREEN')
