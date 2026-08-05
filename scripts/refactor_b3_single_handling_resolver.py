from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, found {count}")
    return text.replace(old, new, 1)

# 1. Remove legacy batch presentation mutation completely.
shared_path = ROOT / 'frontend/src/features/stores/storeImportShared.jsx'
shared = shared_path.read_text(encoding='utf-8-sig')
shared = shared.replace("\nconst DIRECT_CONSUMPTION = 'DIRECT_CONSUMPTION'\n", "\n", 1)
legacy_start = shared.index('function isPurchaseImportBatchRequest(url, options) {')
legacy_end = shared.index('export const articleFallbackOptions', legacy_start)
shared = shared[:legacy_start] + "export async function fetchJson(url, options = {}) {\n  return requestJson(url, options)\n}\n\n" + shared[legacy_end:]
shared_path.write_text(shared, encoding='utf-8')

# 2. Add one central resolver for effective handling and destination.
handling_path = ROOT / 'frontend/src/features/receipts/dayArticleHandling.js'
handling = handling_path.read_text(encoding='utf-8')
anchor = '''export function lineInventoryHandlingPresentation(defaultHandling, lineOverride = null) {
  const effectiveHandling = effectiveInventoryHandling(defaultHandling, lineOverride)
  return {
    ...inventoryHandlingPresentation(effectiveHandling),
    defaultHandling: normalizeInventoryHandling(defaultHandling),
    overrideHandling: normalizeInventoryHandlingOverride(lineOverride),
    isOverride: normalizeInventoryHandlingOverride(lineOverride) !== null,
  }
}
'''
resolver = anchor + '''
export function resolveEffectiveLineDestination({
  defaultHandling,
  lineOverride = null,
  currentLocationId = '',
  directLocationId = '',
}) {
  const presentation = lineInventoryHandlingPresentation(defaultHandling, lineOverride)
  const normalizedCurrentLocationId = String(currentLocationId || '')
  const normalizedDirectLocationId = String(directLocationId || '')

  if (presentation.handling === DIRECT_CONSUMPTION) {
    return {
      ...presentation,
      locationId: normalizedDirectLocationId,
      requiresLocationChange: Boolean(normalizedDirectLocationId)
        && normalizedCurrentLocationId !== normalizedDirectLocationId,
    }
  }

  const locationId = normalizedCurrentLocationId === normalizedDirectLocationId
    ? ''
    : normalizedCurrentLocationId
  return {
    ...presentation,
    locationId,
    requiresLocationChange: locationId !== normalizedCurrentLocationId,
  }
}
'''
handling = replace_once(handling, anchor, resolver, 'add central resolver')
handling_path.write_text(handling, encoding='utf-8')

# 3. Make StoreBatchDetailPage the sole owner of reconciliation.
page_path = ROOT / 'frontend/src/features/stores/StoreBatchDetailPage.jsx'
page = page_path.read_text(encoding='utf-8')
page = replace_once(
    page,
    '  lineInventoryHandlingPresentation,\n  saveInventoryHandlingOverride,\n',
    '  lineInventoryHandlingPresentation,\n  resolveEffectiveLineDestination,\n  saveInventoryHandlingOverride,\n',
    'import central resolver',
)
state_anchor = '  const [inventoryHandlingOverridesByLineId, setInventoryHandlingOverridesByLineId] = useState({})\n'
page = replace_once(
    page,
    state_anchor,
    state_anchor + '  const handlingReconcileRef = useRef(false)\n',
    'add reconciliation ref',
)
insert_anchor = '''  }, [batch?.lines, lineSaveState, lineDrafts, selectedLineIds, validLocationIds, inventoryHandlingByArticleId, inventoryHandlingOverridesByLineId])

  const summaryCounts = useMemo(() => {
'''
reconcile_effect = '''  }, [batch?.lines, lineSaveState, lineDrafts, selectedLineIds, validLocationIds, inventoryHandlingByArticleId, inventoryHandlingOverridesByLineId])

  useEffect(() => {
    if (handlingReconcileRef.current || isLoading || busyLineId || isProcessingBatch) return
    const directLocation = directLocationOption(locationOptions)
    if (!directLocation?.id) return

    const entry = lineUiStates.find((candidate) => {
      if (candidate.processingStatus === 'processed') return false
      const articleId = String(candidate.draft.articleId || candidate.line.matched_household_article_id || '').trim()
      if (!articleId) return false
      const resolution = resolveEffectiveLineDestination({
        defaultHandling: candidate.defaultInventoryHandling,
        lineOverride: candidate.inventoryHandlingOverride,
        currentLocationId: candidate.draft.locationId,
        directLocationId: directLocation.id,
      })
      return resolution.requiresLocationChange
    })
    if (!entry) return

    const resolution = resolveEffectiveLineDestination({
      defaultHandling: entry.defaultInventoryHandling,
      lineOverride: entry.inventoryHandlingOverride,
      currentLocationId: entry.draft.locationId,
      directLocationId: directLocation.id,
    })
    handlingReconcileRef.current = true
    persistLineDraft(
      entry.line,
      { locationId: resolution.locationId },
      { defaultLocationPolicy: 'line_only', suppressSuccessFeedback: true },
    ).catch((reconcileError) => {
      const message = normalizeErrorMessage(reconcileError?.message || reconcileError)
        || 'De effectieve locatie kon niet worden toegepast.'
      showUitpakkenFeedback('error', message, { key: `uitpakken-handling-reconcile-${entry.line.id}-${Date.now()}` })
    }).finally(() => {
      handlingReconcileRef.current = false
    })
  }, [lineUiStates, locationOptions, isLoading, busyLineId, isProcessingBatch])

  const summaryCounts = useMemo(() => {
'''
page = replace_once(page, insert_anchor, reconcile_effect, 'add single reconciliation effect')
page_path.write_text(page, encoding='utf-8')

# 4. Replace old contract with the single-source contract.
contract_path = ROOT / 'frontend/src/features/stores/storeImportShared.day-articles.contract.test.js'
contract_path.write_text("""import fs from 'node:fs'\nimport path from 'node:path'\nimport { describe, expect, it } from 'vitest'\n\nconst root = path.resolve(process.cwd())\nconst shared = fs.readFileSync(path.join(root, 'src/features/stores/storeImportShared.jsx'), 'utf8')\nconst page = fs.readFileSync(path.join(root, 'src/features/stores/StoreBatchDetailPage.jsx'), 'utf8')\nconst handling = fs.readFileSync(path.join(root, 'src/features/receipts/dayArticleHandling.js'), 'utf8')\n\ndescribe('B3 single handling resolver contract', () => {\n  it('removes the legacy batch presentation mutation', () => {\n    expect(shared).not.toContain('addDayArticlePresentation')\n    expect(shared).not.toContain('isPurchaseImportBatchRequest')\n    expect(shared).not.toContain('day_article_location_locked')\n    expect(shared).toContain('return requestJson(url, options)')\n  })\n\n  it('centralizes effective handling and destination', () => {\n    expect(handling).toContain('export function resolveEffectiveLineDestination')\n    expect(handling).toContain('lineInventoryHandlingPresentation(defaultHandling, lineOverride)')\n    expect(handling).toContain('requiresLocationChange')\n  })\n\n  it('uses the resolver during initial load and reload', () => {\n    expect(page).toContain('resolveEffectiveLineDestination({')\n    expect(page).toContain('handlingReconcileRef')\n    expect(page).toContain("{ defaultLocationPolicy: 'line_only', suppressSuccessFeedback: true }")\n  })\n})\n""", encoding='utf-8')

# 5. Remove obsolete separate selector and test; Locatie is the only control.
for relative in [
    'frontend/src/features/receipts/InventoryHandlingOverrideSelect.jsx',
    'frontend/src/features/receipts/InventoryHandlingOverrideSelect.contract.test.js',
]:
    target = ROOT / relative
    if target.exists():
        target.unlink()

print('B3_SINGLE_RESOLVER_REFACTOR_APPLIED')
