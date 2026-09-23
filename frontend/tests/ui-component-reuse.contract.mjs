import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  APPROVED_UI_COMPONENTS,
  EXISTING_UI_MODULES_REQUIRING_FUTURE_REVIEW,
  MIGRATED_SCREEN_COMPONENT_REQUIREMENTS,
} from '../src/ui/componentCatalog.js'
import {
  MAX_TRANSIENT_FEEDBACK_MS,
  isTransientFeedback,
  transientFeedbackDuration,
} from '../src/ui/feedbackPolicy.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')

const ids = new Set()
for (const component of APPROVED_UI_COMPONENTS) {
  assert.ok(component.id && !ids.has(component.id), `Ongeldig/dubbel component-id: ${component.id}`)
  ids.add(component.id)
  assert.ok(component.source && existsSync(path.join(frontendRoot, component.source)), `Bron ontbreekt: ${component.source}`)
  assert.ok(component.publicApi)
  assert.ok(component.purpose)
  assert.ok(component.reuseRule)
  assert.ok(Array.isArray(component.contractTests) && component.contractTests.length > 0)
  for (const contract of component.contractTests) {
    assert.ok(existsSync(path.join(frontendRoot, contract)), `Contracttest ontbreekt: ${contract}`)
  }
}

const registeredSources = new Set([
  ...APPROVED_UI_COMPONENTS.map((item) => item.source),
  ...EXISTING_UI_MODULES_REQUIRING_FUTURE_REVIEW,
])
const uiJsxFiles = readdirSync(path.join(frontendRoot, 'src/ui'))
  .filter((name) => name.endsWith('.jsx'))
  .map((name) => `src/ui/${name}`)
for (const source of uiJsxFiles) {
  assert.ok(
    registeredSources.has(source),
    `Nieuw centraal UI-component ${source} is niet gespecificeerd in componentCatalog.js`,
  )
}

for (const screen of MIGRATED_SCREEN_COMPONENT_REQUIREMENTS) {
  const source = readFileSync(path.join(frontendRoot, screen.source), 'utf8')
  for (const token of screen.requiredTokens) {
    assert.match(source, new RegExp(token))
  }
}

const mobileInventory = readFileSync(path.join(frontendRoot, 'src/pages/MobileVoorraad.jsx'), 'utf8')
const mobileInventoryCss = readFileSync(path.join(frontendRoot, 'src/pages/mobileVoorraad.css'), 'utf8')
assert.match(mobileInventory, /useAppFeedback\(\)/)
assert.match(mobileInventory, /<MobileModuleHeader/)
assert.match(mobileInventory, /<MobileRecentActionsBar/)
assert.match(mobileInventory, /<QuantityStepper/)
assert.doesNotMatch(mobileInventory, /setMutationFeedback|mutationFeedback/)
assert.doesNotMatch(mobileInventoryCss, /rz-mobile-inventory-quick-feedback|rz-mobile-inventory-topbar|rz-mobile-inventory-bottom-nav/)

const transient = {
  variant: 'success',
  dismissMode: 'outside-or-ok',
  inputFields: [],
  onPrimaryAction: null,
  onSecondaryAction: null,
  showTechnicalToggle: false,
}
assert.equal(MAX_TRANSIENT_FEEDBACK_MS, 3000)
assert.equal(isTransientFeedback(transient), true)
assert.equal(transientFeedbackDuration(transient), 3000)
assert.equal(transientFeedbackDuration({ ...transient, autoDismissMs: 8000 }), 3000)
assert.equal(transientFeedbackDuration({ ...transient, autoDismissMs: 1200 }), 1200)
assert.equal(isTransientFeedback({ ...transient, variant: 'progress', dismissMode: 'blocked' }), false)
assert.equal(isTransientFeedback({ ...transient, onPrimaryAction: () => true }), false)
assert.equal(isTransientFeedback({ ...transient, showTechnicalToggle: true }), false)

console.log('UI_COMPONENT_REUSE_CONTRACT_GREEN')
