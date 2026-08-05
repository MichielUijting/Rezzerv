import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const root = path.resolve(process.cwd())
const shared = fs.readFileSync(path.join(root, 'src/features/stores/storeImportShared.jsx'), 'utf8')
const page = fs.readFileSync(path.join(root, 'src/features/stores/StoreBatchDetailPage.jsx'), 'utf8')
const handling = fs.readFileSync(path.join(root, 'src/features/receipts/dayArticleHandling.js'), 'utf8')

describe('B3 single handling resolver contract', () => {
  it('removes the legacy batch presentation mutation', () => {
    expect(shared).not.toContain('addDayArticlePresentation')
    expect(shared).not.toContain('isPurchaseImportBatchRequest')
    expect(shared).not.toContain('day_article_location_locked')
    expect(shared).toContain('return requestJson(url, options)')
  })

  it('centralizes effective handling and destination', () => {
    expect(handling).toContain('export function resolveEffectiveLineDestination')
    expect(handling).toContain('lineInventoryHandlingPresentation(defaultHandling, lineOverride)')
    expect(handling).toContain('requiresLocationChange')
  })

  it('uses the resolver during initial load and reload', () => {
    expect(page).toContain('resolveEffectiveLineDestination({')
    expect(page).toContain('handlingReconcileRef')
    expect(page).toContain("{ defaultLocationPolicy: 'line_only', suppressSuccessFeedback: true }")
  })
})
