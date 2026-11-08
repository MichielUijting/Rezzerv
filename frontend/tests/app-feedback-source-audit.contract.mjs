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
assert.match(provider, /interactiveDialog = !mobileTransient \|\| variant === 'error'/)
assert.match(provider, /background: '#FFFFFF'/)
assert.match(provider, /setFeedback\(\(current\) => current\?\.id === feedback\.id \? null : current\)/,
  'Een succesvolle actie mag opvolgende feedback niet wissen')
const unpacking = fs.readFileSync(path.join(root, 'features/stores/StoreBatchDetailPage.jsx'), 'utf8')
const resultFeedback = unpacking.split('if (processedCount > 0 || skippedCount > 0 || failedCount > 0) {')[1]
  ?.split('setSelectedLineIds((current) => current.filter')[0]
assert.ok(resultFeedback, 'Uitpakken moet het resultaat van een bulkverwerking tonen')
assert.match(resultFeedback, /dismissMode: 'ok-only'/,
  'Ook een gedeeltelijke bulkverwerking blijft zichtbaar tot OK')
assert.match(resultFeedback, /skippedCount > 0 \? 'warning' : 'success'/,
  'Overgeslagen regels krijgen een herkenbare waarschuwing in de centrale resultaatmelding')
assert.match(resultFeedback, /failedCount > 0\s*\? 'Verwerking deels mislukt'/,
  'Mislukte regels worden nooit als succesvolle verwerking gepresenteerd')
assert.doesNotMatch(resultFeedback, /showUitpakkenFeedback\(/,
  'Een bulkresultaat mag niet terugvallen op de tijdelijke waarschuwing')

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
  'features/almostOut/AlmostOutPage.jsx',
  'features/almostOut/MobileAlmostOut.jsx',
  'features/articleSynonyms/SynonymAnalysisPage.jsx',
  'features/articles/MobileArticlePage.jsx',
  'features/articles/tabs/ArticleLocationsTab.jsx',
  'features/articles/tabs/ArticleOverviewTab.jsx',
  'features/articles/tabs/ArticleStockTab.jsx',
  'features/auth/ForgotPasswordPage.jsx',
  'features/auth/LoginPage.jsx',
  'features/auth/RegisterPage.jsx',
  'features/auth/ResetPasswordPage.jsx',
  'features/barcodes/BarcodeScannerModal.jsx',
  'features/catalog/CatalogBarcodeEntry.jsx',
  'features/catalog/CatalogCameraModal.jsx',
  'features/catalog/CatalogDetailPage.jsx',
  'features/catalog/CatalogDetailPageV2.jsx',
  'features/catalog/CatalogGpcActionPage.jsx',
  'features/catalog/CatalogGpcFrame.jsx',
  'features/catalog/CatalogNameEditor.jsx',
  'features/catalog/CatalogPage.jsx',
  'features/catalog/CbsClassificationPage.jsx',
  'features/catalog/MobileCatalogPage.jsx',
  'features/catalog/ShopifyReviewPage.jsx',
  'features/externalDatabases/CombinedClassificationWorkspace.jsx',
  'features/externalDatabases/Ed2GpcClassificationPanel.jsx',
  'features/externalDatabases/ExternalDatabases2Page.jsx',
  'features/externalDatabases/OffCandidatePanel.jsx',
  'features/externalDatabases/OffManualSearchPage.jsx',
  'features/home/DashboardDetailPage.jsx',
  'features/home/MobileHomePage.jsx',
  'features/kassa/MobileKassa.jsx',
  'features/kassa/components/ReceiptPreviewCard.jsx',
  'features/onboarding/SharedHouseholdMinimumPage.jsx',
  'features/platform/IpOwnerSuperusersPage.jsx',
  'features/platform/PlatformAuditPage.jsx',
  'features/platform/PlatformAuthorizationsPage.jsx',
  'features/platform/PlatformBackgroundJobsPage.jsx',
  'features/platform/PlatformDiagnosticsPage.jsx',
  'features/platform/PlatformFeatureFlagsPage.jsx',
  'features/platform/PlatformIntegrationsPage.jsx',
  'features/platform/PlatformLogsPage.jsx',
  'features/platform/PlatformMaintenancePanel.jsx',
  'features/platform/PlatformRecoveryPage.jsx',
  'features/platform/PlatformSessionsPage.jsx',
  'features/platform/PlatformTechnicalConfigurationPage.jsx',
  'features/platform/PlatformTestFixturesPage.jsx',
  'features/platform/PlatformUsersPage.jsx',
  'features/receipts/KassaPage.jsx',
  'features/settings/SettingsAlmostOutPage.jsx',
  'features/settings/SettingsArticleFieldsPage.jsx',
  'features/settings/SettingsArticleGroupsPage.jsx',
  'features/settings/SettingsCapabilitiesPage.jsx',
  'features/settings/SettingsFrontteamPage.jsx',
  'features/settings/SettingsHouseholdAutomationPage.jsx',
  'features/settings/SettingsLocationsPage.jsx',
  'features/settings/SettingsMyAccountPage.jsx',
  'features/settings/SettingsPrivacyDataSharingPage.jsx',
  'features/settings/SettingsSpacesPage.jsx',
  'features/settings/SettingsStoreImportPage.jsx',
  'features/settings/SettingsSublocationsPage.jsx',
  'features/shopping/MobileShopping.jsx',
  'features/shopping/ShoppingPage.jsx',
  'features/storeConnections/PicnicAccountResearchPanel.jsx',
  'features/storeConnections/RetailerReceiptPanel.jsx',
  'features/storeConnections/StoreConnectionsPage.jsx',
  'features/stores/StoreBatchDetailPage.jsx',
  'features/stores/StoresPage.jsx',
  'features/stores/storeImportShared.jsx',
  'features/superuser/SuperuserActionButtonsSection.jsx',
  'features/superuser/SuperuserAppearanceSection.jsx',
  'features/superuser/SuperuserDashboardPage.jsx',
  'features/superuser/SuperuserLoginBackgroundSection.jsx',
  'features/superuser/SuperuserOverviewSection.jsx',
  'features/superuser/SuperuserUsageSection.jsx',
  'features/superuser/SuperuserUsersSection.jsx',
  'features/support/MobileSupportInbox.jsx',
  'pages/IncidentalPurchasePage.jsx',
  'pages/MobileVoorraad.jsx',
  'pages/ReceiptReviewPreviewPage.jsx',
  'pages/Voorraad.jsx',
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
