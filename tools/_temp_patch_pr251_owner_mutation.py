from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
overview_path = ROOT / "frontend/src/features/articles/tabs/ArticleOverviewTab.jsx"
test_path = ROOT / "backend/tests/test_article_detail_mutation_contract.py"
workflow_path = ROOT / ".github/workflows/article-detail-write-guard.yml"
smoke_path = ROOT / "frontend/tests/e2e/article-detail-owner-mutation.smoke.mjs"


def replace_exact(text: str, old: str, new: str, expected_count: int, label: str) -> str:
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{label}: verwacht {expected_count} occurrence(s), gevonden {count}")
    return text.replace(old, new)


# 1) Frontend role ownership: use central auth SSOT, fail closed without session.
overview = overview_path.read_text(encoding="utf-8")
overview = replace_exact(
    overview,
    "import { fetchJsonWithAuth, readStoredAuthContext } from '../../../lib/authSession'",
    "import { fetchJsonWithAuth, isHouseholdAdminFromContext, isHouseholdViewerFromContext, readStoredAuthContext } from '../../../lib/authSession'",
    1,
    "auth import",
)
overview = replace_exact(
    overview,
    "  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()\n  const canEdit = displayRole === 'admin'\n",
    "  const canEdit = isHouseholdAdminFromContext(authContext)\n",
    1,
    "admin-only automation role gate",
)
overview = replace_exact(
    overview,
    "  const displayRole = String(authContext?.display_role || '').trim().toLowerCase()\n  const canEdit = displayRole === 'admin' || displayRole === 'lid'\n",
    "  const canEdit = Boolean(authContext) && !isHouseholdViewerFromContext(authContext)\n",
    3,
    "household writer role gates",
)
overview_path.write_text(overview, encoding="utf-8")

# 2) Strengthen executable/static mutation contract around central role SSOT.
tests = test_path.read_text(encoding="utf-8")
tests = replace_exact(
    tests,
    "    assert \"displayRole === 'admin' || displayRole === 'lid'\" in external\n",
    "    assert \"const canEdit = Boolean(authContext) && !isHouseholdViewerFromContext(authContext)\" in external\n",
    1,
    "external role assertion",
)
tests = replace_exact(
    tests,
    "    assert \"const canEdit = displayRole === 'admin'\" in automation\n",
    "    assert \"const canEdit = isHouseholdAdminFromContext(authContext)\" in automation\n",
    1,
    "automation role assertion",
)
insert_marker = "\ndef test_external_product_identity_uses_dedicated_flow_and_role_gate():\n"
new_test = '''\ndef test_household_mutation_cards_use_central_role_ssot_and_fail_closed():
    source = _read(OVERVIEW_PATH)
    assert "isHouseholdAdminFromContext" in source
    assert "isHouseholdViewerFromContext" in source

    general = _between(source, "function ArticleDetailsEditor", "function normalizeSettingsFormValue")
    settings = _between(source, "function HouseholdArticleSettingsCard", "function ProductDetailsCard")
    external = _between(source, "function ExternalLinkCard", "export default function ArticleOverviewTab")
    for section in (general, settings, external):
        assert "const canEdit = Boolean(authContext) && !isHouseholdViewerFromContext(authContext)" in section
        assert "displayRole === 'admin' || displayRole === 'lid'" not in section

'''
if new_test.strip() in tests:
    raise SystemExit("central role SSOT regression test already present")
if tests.count(insert_marker) != 1:
    raise SystemExit("test insertion marker mismatch")
tests = tests.replace(insert_marker, new_test + insert_marker, 1)
run_marker = "    test_household_settings_have_one_dedicated_mutation_owner()\n"
run_add = run_marker + "    test_household_mutation_cards_use_central_role_ssot_and_fail_closed()\n"
tests = replace_exact(tests, run_marker, run_add, 1, "run_contract central role test")
test_path.write_text(tests, encoding="utf-8")

# 3) Browser smoke: actually open the touched route for owner and viewer.
smoke = r'''import { chromium } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174'
const articleId = 'article-owner-smoke'
const articleName = '7 Granen Ontbijt'

function sessionPayload(role) {
  const owner = role === 'owner'
  return {
    user_id: owner ? 'owner-user' : 'viewer-user',
    email: owner ? 'owner@rezzerv.test' : 'viewer@rezzerv.test',
    active_household_id: '1',
    active_household_name: 'Smoke huishouden',
    role,
    display_role: role,
    membership_count: 1,
    can_switch_households: false,
    permissions: owner ? { 'admin.access': true } : {},
    is_viewer: !owner,
  }
}

async function installApiMocks(page, role) {
  let customName = 'Oude naam'
  const writes = []
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const json = async (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (path === '/api/session') return json(sessionPayload(role))
    if (path === '/api/household') return json(sessionPayload(role))
    if (path === '/api/settings/article-field-visibility') {
      return json({ overview: { article_name: true, custom_name: true }, stock: {}, locations: {}, history: {}, analytics: {} })
    }
    if (path === '/api/dev/inventory-preview') {
      return json({ rows: [{ id: articleId, artikel: articleName, aantal: 1, locatie: 'Voorraadkast', sublocatie: 'Plank 1' }] })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'GET') {
      return json({
        id: articleId,
        article_id: articleId,
        household_article_id: articleId,
        article_name: articleName,
        custom_name: customName,
        article_type: 'Voedsel & drank',
        total_quantity: 1,
        settings: {
          min_stock: 1,
          ideal_stock: 2,
          favorite_store: '',
          average_price: null,
          status: 'active',
          default_location_id: null,
          default_sublocation_id: null,
          auto_restock: false,
          packaging_unit: '',
          packaging_quantity: null,
          notes: '',
        },
      })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'PATCH') {
      const body = request.postDataJSON()
      writes.push(body)
      customName = String(body?.custom_name || '')
      return json({ details: { article_id: articleId, household_article_id: articleId, article_name: articleName, custom_name: customName, article_type: 'Voedsel & drank' } })
    }
    if (path === `/api/household-articles/${articleId}/events`) return json({ items: [] })
    if (path === `/api/household-articles/${articleId}/automation-override`) {
      return json({ article_id: articleId, household_article_id: articleId, mode: 'follow_household', has_explicit_override: false, consumable: true })
    }
    if (path === '/api/spaces' || path === '/api/sublocations') return json({ items: [] })
    return json({})
  })
  return writes
}

async function verifyOwner(browser) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, 'owner')
  const consoleErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  const ownName = page.getByTestId('article-details-input-custom_name')
  await ownName.waitFor({ state: 'visible' })
  if (await ownName.isDisabled()) throw new Error('owner: Eigen naam is ten onrechte disabled')

  const settingsSave = page.getByTestId('article-household-settings-save')
  if (await settingsSave.isDisabled()) throw new Error('owner: huishoudinstellingen zijn ten onrechte disabled')
  if (await page.getByTestId('article-external-link-edit').count() !== 1) throw new Error('owner: externe productkoppeling is niet muteerbaar')
  const automation = page.locator('.rz-article-automation-select')
  if (await automation.isDisabled()) throw new Error('owner: Admin/Eigenaar automatisering is ten onrechte disabled')

  await ownName.fill('PO OWNER SMOKE')
  await ownName.blur()
  await page.getByTestId('article-details-save-success').waitFor({ state: 'visible' })
  if (writes.length !== 1 || writes[0]?.custom_name !== 'PO OWNER SMOKE' || Object.keys(writes[0]).length !== 1) {
    throw new Error(`owner: onjuist PATCH-contract ${JSON.stringify(writes)}`)
  }
  if (consoleErrors.length) throw new Error(`owner: console errors: ${consoleErrors.join(' | ')}`)
  await page.close()
}

async function verifyViewer(browser) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, 'viewer')
  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  const ownName = page.getByTestId('article-details-input-custom_name')
  await ownName.waitFor({ state: 'visible' })
  if (!(await ownName.isDisabled())) throw new Error('viewer: Eigen naam moet disabled zijn')
  if (!(await page.getByTestId('article-household-settings-save').isDisabled())) throw new Error('viewer: huishoudinstellingen moeten disabled zijn')
  if (await page.getByTestId('article-external-link-edit').count()) throw new Error('viewer: externe productkoppeling mag geen muteeractie tonen')
  if (!(await page.locator('.rz-article-automation-select').isDisabled())) throw new Error('viewer: automatisering moet disabled zijn')
  if (writes.length) throw new Error(`viewer: onverwachte write ${JSON.stringify(writes)}`)
  await page.close()
}

const browser = await chromium.launch({ headless: true })
try {
  await verifyOwner(browser)
  await verifyViewer(browser)
  console.log('ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN')
} finally {
  await browser.close()
}
'''
smoke_path.write_text(smoke, encoding="utf-8")

# 4) Extend Article detail write guard with actual browser route smoke.
workflow = workflow_path.read_text(encoding="utf-8")
workflow_marker = "      - name: Bouw gewijzigde frontend\n        working-directory: frontend\n        run: |\n          npm install --no-audit --no-fund\n          npm run build\n"
workflow_replacement = workflow_marker + "\n      - name: Open Artikeldetail echt als Eigenaar en Kijker\n        working-directory: frontend\n        env:\n          PLAYWRIGHT_BASE_URL: http://127.0.0.1:5174\n        run: |\n          npx playwright install --with-deps chromium\n          npm run dev -- --host 127.0.0.1 --port 5174 > /tmp/rezzerv-vite.log 2>&1 &\n          vite_pid=$!\n          trap 'kill $vite_pid 2>/dev/null || true' EXIT\n          for attempt in {1..30}; do\n            if curl --fail --silent http://127.0.0.1:5174/version.json >/dev/null; then\n              break\n            fi\n            if [ \"$attempt\" = \"30\" ]; then\n              cat /tmp/rezzerv-vite.log\n              exit 1\n            fi\n            sleep 1\n          done\n          node tests/e2e/article-detail-owner-mutation.smoke.mjs | tee /tmp/article-detail-owner-smoke.log\n          grep -F 'ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN' /tmp/article-detail-owner-smoke.log\n"
if "ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN" in workflow:
    raise SystemExit("browser smoke already wired into workflow")
workflow = replace_exact(workflow, workflow_marker, workflow_replacement, 1, "article detail workflow build marker")
workflow_path.write_text(workflow, encoding="utf-8")

# 5) Mandatory new release identity after functional NO-GO: v01.12.96.
version_pairs = {
    ROOT / "VERSION.txt": ("Rezzerv-MVP-v01.12.95\n", "Rezzerv-MVP-v01.12.96\n"),
    ROOT / "backend/VERSION.txt": ("Rezzerv-MVP-v01.12.95\n", "Rezzerv-MVP-v01.12.96\n"),
    ROOT / "version.json": ('{"version": "Rezzerv-MVP-v01.12.95"}\n', '{"version": "Rezzerv-MVP-v01.12.96"}\n'),
    ROOT / "frontend/version.json": ('{"version": "Rezzerv-MVP-v01.12.95"}\n', '{"version": "Rezzerv-MVP-v01.12.96"}\n'),
    ROOT / "frontend/public/version.json": ('{"version": "Rezzerv-MVP-v01.12.95"}\n', '{"version": "Rezzerv-MVP-v01.12.96"}\n'),
}
for path, (old, new) in version_pairs.items():
    text = path.read_text(encoding="utf-8")
    if text != old:
        raise SystemExit(f"version precondition failed for {path}: {text!r}")
    path.write_text(new, encoding="utf-8")

package_path = ROOT / "frontend/package.json"
package = json.loads(package_path.read_text(encoding="utf-8"))
if package.get("version") != "1.12.95":
    raise SystemExit(f"frontend package version precondition failed: {package.get('version')}")
package["version"] = "1.12.96"
package_path.write_text(json.dumps(package, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")

print("PR251_OWNER_MUTATION_PATCH_READY")
