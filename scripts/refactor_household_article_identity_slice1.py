from pathlib import Path

AUTH = Path('frontend/src/lib/authSession.js')
PAGE = Path('frontend/src/features/stores/StoreBatchDetailPage.jsx')
TEST = Path('frontend/src/features/stores/householdArticleIdentity.single-source.contract.test.js')

auth = AUTH.read_text(encoding='utf-8')
page = PAGE.read_text(encoding='utf-8')

adapter_import = """import {\n  normalizeHouseholdArticleOptionsPayload,\n  shouldNormalizeHouseholdArticleOptions,\n} from '../features/stores/householdArticleOptionAdapter.js'\n\n"""
if adapter_import not in auth:
    raise SystemExit('AUTH_ADAPTER_IMPORT_NOT_FOUND')
auth = auth.replace(adapter_import, '', 1)

normalization_block = """\n  if (response.ok && shouldNormalizeHouseholdArticleOptions(url, restOptions.method || 'GET')) {\n    try {\n      const payload = await response.clone().json()\n      return jsonResponseFrom(response, normalizeHouseholdArticleOptionsPayload(payload))\n    } catch {}\n  }\n"""
if normalization_block not in auth:
    raise SystemExit('AUTH_GLOBAL_NORMALIZATION_NOT_FOUND')
auth = auth.replace(normalization_block, '', 1)

page_import_anchor = "import BarcodeScannerModal from '../barcodes/BarcodeScannerModal.jsx'\n"
page_import = "import { normalizeHouseholdArticleOptionsPayload } from './householdArticleOptionAdapter.js'\n"
if page_import not in page:
    if page_import_anchor not in page:
        raise SystemExit('PAGE_IMPORT_ANCHOR_NOT_FOUND')
    page = page.replace(page_import_anchor, page_import_anchor + page_import, 1)

old_set = """      setArticleOptions(sortOptionObjects(Array.isArray(backendArticles) ? backendArticles : (backendArticles?.items || []), (article) => article?.name || ''))\n"""
new_set = """      const canonicalArticlePayload = normalizeHouseholdArticleOptionsPayload(backendArticles)\n      const canonicalArticleItems = Array.isArray(canonicalArticlePayload)\n        ? canonicalArticlePayload\n        : (canonicalArticlePayload?.items || [])\n      setArticleOptions(sortOptionObjects(canonicalArticleItems, (article) => article?.name || ''))\n"""
if old_set not in page:
    raise SystemExit('PAGE_ARTICLE_OPTIONS_SET_NOT_FOUND')
page = page.replace(old_set, new_set, 1)

contract = """import fs from 'node:fs'\nimport path from 'node:path'\nimport { describe, expect, it } from 'vitest'\n\nconst root = path.resolve(process.cwd())\nconst auth = fs.readFileSync(path.join(root, 'src/lib/authSession.js'), 'utf8')\nconst page = fs.readFileSync(path.join(root, 'src/features/stores/StoreBatchDetailPage.jsx'), 'utf8')\n\ndescribe('Huishoudartikel single-source slice 1', () => {\n  it('verwijdert verborgen artikel-ID-normalisatie uit de globale auth/fetch-laag', () => {\n    expect(auth).not.toContain('normalizeHouseholdArticleOptionsPayload')\n    expect(auth).not.toContain('shouldNormalizeHouseholdArticleOptions')\n    expect(auth).not.toContain('store-review-articles')\n  })\n\n  it('begrenst tijdelijke compatibiliteitsnormalisatie tot Uitpakken', () => {\n    expect(page).toContain("normalizeHouseholdArticleOptionsPayload(backendArticles)")\n    expect(page).toContain('canonicalArticleItems')\n  })\n\n  it('blijft echte household_article_id gebruiken voor B2/B3/B4', () => {\n    expect(page).toContain('line?.matched_household_article_id')\n    expect(page).toContain('fetchInventoryHandlingByArticleIds')\n  })\n})\n"""

AUTH.write_text(auth, encoding='utf-8')
PAGE.write_text(page, encoding='utf-8')
TEST.write_text(contract, encoding='utf-8')
print('HOUSEHOLD_ARTICLE_IDENTITY_SLICE1_APPLIED')
