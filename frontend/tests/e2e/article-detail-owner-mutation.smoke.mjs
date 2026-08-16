import { chromium } from '@playwright/test'

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
  const patchResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}` && response.request().method() === 'PATCH'
  })
  await ownName.blur()
  const patchResponse = await patchResponsePromise
  if (!patchResponse.ok()) throw new Error(`owner: PATCH gaf HTTP ${patchResponse.status()}`)
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
