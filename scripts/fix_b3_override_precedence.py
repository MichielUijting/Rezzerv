from pathlib import Path

shared_path = Path('frontend/src/features/stores/storeImportShared.jsx')
text = shared_path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 occurrence, found {count}')
    text = text.replace(old, new, 1)

replace_once(
    "  const articleIds = Array.from(new Set(\n    lines\n      .map((line) => String(line?.matched_household_article_id || '').trim())\n      .filter(Boolean),\n  ))\n  if (!householdId || articleIds.length === 0) return batch\n",
    "  const articleIds = Array.from(new Set(\n    lines\n      .map((line) => String(line?.matched_household_article_id || '').trim())\n      .filter(Boolean),\n  ))\n  const lineIds = Array.from(new Set(\n    lines\n      .map((line) => String(line?.id || '').trim())\n      .filter(Boolean),\n  ))\n  if (!householdId || articleIds.length === 0) return batch\n",
    'collect line ids',
)

replace_once(
    "    const [handlingData, spacesData, sublocationsData] = await Promise.all([\n      requestJson(\n        `/api/households/${encodeURIComponent(householdId)}/articles/inventory-handling/batch`,\n        {\n          method: 'POST',\n          body: JSON.stringify({ household_article_ids: articleIds }),\n        },\n      ),\n      requestJson('/api/spaces?_day_articles=1'),\n      requestJson('/api/sublocations?_day_articles=1'),\n    ])\n",
    "    const [handlingData, overrideData, spacesData, sublocationsData] = await Promise.all([\n      requestJson(\n        `/api/households/${encodeURIComponent(householdId)}/articles/inventory-handling/batch`,\n        {\n          method: 'POST',\n          body: JSON.stringify({ household_article_ids: articleIds }),\n        },\n      ),\n      requestJson(\n        `/api/households/${encodeURIComponent(householdId)}/purchase-import-lines/inventory-handling-overrides/batch`,\n        {\n          method: 'POST',\n          body: JSON.stringify({ purchase_import_line_ids: lineIds }),\n        },\n      ),\n      requestJson('/api/spaces?_day_articles=1'),\n      requestJson('/api/sublocations?_day_articles=1'),\n    ])\n",
    'load line overrides',
)

replace_once(
    "    const protectedDirectLocationId = directLocationId(spacesData, sublocationsData)\n\n    return {\n",
    "    const overrideByLineId = Object.fromEntries(\n      (Array.isArray(overrideData?.items) ? overrideData.items : []).map((item) => [\n        String(item?.purchase_import_line_id || ''),\n        String(item?.inventory_handling_override || '').trim().toUpperCase(),\n      ]),\n    )\n    const protectedDirectLocationId = directLocationId(spacesData, sublocationsData)\n\n    return {\n",
    'index line overrides',
)

replace_once(
    "        const articleId = String(line?.matched_household_article_id || '').trim()\n        const isDirect = handlingByArticleId[articleId] === DIRECT_CONSUMPTION\n        if (!isDirect || !protectedDirectLocationId) return line\n",
    "        const articleId = String(line?.matched_household_article_id || '').trim()\n        const lineId = String(line?.id || '').trim()\n        const articleDefault = handlingByArticleId[articleId] || 'STOCK'\n        const lineOverride = overrideByLineId[lineId] || ''\n        const effectiveHandling = lineOverride || articleDefault\n        const isDirect = effectiveHandling === DIRECT_CONSUMPTION\n        if (!isDirect || !protectedDirectLocationId) return line\n",
    'apply override precedence',
)

shared_path.write_text(text, encoding='utf-8')

test_path = Path('frontend/src/features/stores/storeImportShared.day-articles.contract.test.js')
test = test_path.read_text(encoding='utf-8')
needle = "    expect(sharedSource).toContain('suggested_location_id: protectedDirectLocationId')\n"
replacement = needle + "    expect(sharedSource).toContain('/purchase-import-lines/inventory-handling-overrides/batch')\n    expect(sharedSource).toContain('const effectiveHandling = lineOverride || articleDefault')\n"
if test.count(needle) != 1:
    raise SystemExit('test contract insertion point not found exactly once')
test_path.write_text(test.replace(needle, replacement, 1), encoding='utf-8')
