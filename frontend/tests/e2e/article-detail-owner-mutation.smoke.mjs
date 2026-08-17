import { chromium } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174'
const articleId = 'article-owner-smoke'
const articleName = '7 Granen Ontbijt'

function sessionPayload(role) {
  const mutable = role === 'owner' || role === 'admin'
  return {
    user_id: `${role}-user`,
    email: `${role}@rezzerv.test`,
    active_household_id: '1',
    active_household_name: 'Smoke huishouden',
    role,
    display_role: role,
    membership_count: 1,
    can_switch_households: false,
    permissions: mutable ? { 'admin.access': true } : {},
    is_viewer: !mutable,
  }
}

async function installApiMocks(page, role) {
  let customName = 'Oude naam'
  let settings = {
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
  }
  let automationMode = 'follow_household'
  const writes = {
    details: [],
    settings: [],
    automation: [],
    externalLinks: [],
  }

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
        barcode: '8712345678901',
        article_number: 'EXT-123',
        settings,
      })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'PATCH') {
      const body = request.postDataJSON()
      writes.details.push(body)
      customName = String(body?.custom_name || '')
      return json({ details: { article_id: articleId, household_article_id: articleId, article_name: articleName, custom_name: customName, article_type: 'Voedsel & drank', barcode: '8712345678901', article_number: 'EXT-123', settings } })
    }
    if (path === `/api/household-articles/${articleId}/settings` && method === 'PUT') {
      const body = request.postDataJSON()
      writes.settings.push(body)
      settings = { ...settings, ...body }
      return json({ settings })
    }
    if (path === `/api/household-articles/${articleId}/events`) return json({ items: [] })
    if (path === `/api/household-articles/${articleId}/automation-override` && method === 'GET') {
      return json({ article_id: articleId, household_article_id: articleId, mode: automationMode, has_explicit_override: automationMode !== 'follow_household', consumable: true })
    }
    if (path === `/api/household-articles/${articleId}/automation-override` && method === 'PUT') {
      const body = request.postDataJSON()
      writes.automation.push(body)
      automationMode = String(body?.mode || 'follow_household')
      return json({ article_id: articleId, household_article_id: articleId, mode: automationMode, has_explicit_override: true, consumable: true })
    }
    if (path === '/api/spaces' || path === '/api/sublocations') return json({ items: [] })
    if (path.includes('/external-product-link')) {
      writes.externalLinks.push(request.postDataJSON())
      return json({})
    }
    return json({})
  })
  return writes
}

async function verifyMutableRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, role)
  const consoleErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })

  const ownName = page.getByTestId('article-details-input-custom_name')
  await ownName.waitFor({ state: 'visible' })
  if (await ownName.isDisabled()) throw new Error(`${role}: Eigen naam is ten onrechte disabled`)

  const settingsSave = page.getByTestId('article-household-settings-save')
  if (await settingsSave.isDisabled()) throw new Error(`${role}: huishoudinstellingen zijn ten onrechte disabled`)

  const barcodeAction = page.getByTestId('article-external-link-edit')
  if (await barcodeAction.isVisible()) throw new Error(`${role}: barcode/externe-link-mutatie mag niet zichtbaar zijn op Artikeldetail`)

  const automation = page.locator('.rz-article-automation-select')
  if (await automation.isDisabled()) throw new Error(`${role}: automatisering is ten onrechte disabled`)

  await ownName.fill(`PO ${role.toUpperCase()} SMOKE`)
  const patchResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}` && response.request().method() === 'PATCH'
  })
  await ownName.blur()
  const patchResponse = await patchResponsePromise
  if (!patchResponse.ok()) throw new Error(`${role}: PATCH gaf HTTP ${patchResponse.status()}`)

  const notes = page.getByTestId('article-details-input-notes')
  await notes.fill(`Notitie ${role}`)
  const settingsResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/settings` && response.request().method() === 'PUT'
  })
  await settingsSave.click()
  const settingsResponse = await settingsResponsePromise
  if (!settingsResponse.ok()) throw new Error(`${role}: settings PUT gaf HTTP ${settingsResponse.status()}`)

  const automationResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/automation-override` && response.request().method() === 'PUT'
  })
  await automation.selectOption('always_on')
  const automationResponse = await automationResponsePromise
  if (!automationResponse.ok()) throw new Error(`${role}: automation PUT gaf HTTP ${automationResponse.status()}`)

  if (writes.details.length !== 1 || writes.details[0]?.custom_name !== `PO ${role.toUpperCase()} SMOKE` || Object.keys(writes.details[0]).length !== 1) {
    throw new Error(`${role}: onjuist PATCH-contract ${JSON.stringify(writes.details)}`)
  }
  if (writes.settings.length !== 1 || writes.settings[0]?.notes !== `Notitie ${role}`) {
    throw new Error(`${role}: huishoudinstellingen zijn niet werkelijk geschreven ${JSON.stringify(writes.settings)}`)
  }
  if (writes.automation.length !== 1 || writes.automation[0]?.mode !== 'always_on') {
    throw new Error(`${role}: automatisering is niet werkelijk geschreven ${JSON.stringify(writes.automation)}`)
  }
  if (writes.externalLinks.length) {
    throw new Error(`${role}: onverwachte externe-productmutatie ${JSON.stringify(writes.externalLinks)}`)
  }
  if (consoleErrors.length) throw new Error(`${role}: console errors: ${consoleErrors.join(' | ')}`)
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
  if (await page.getByTestId('article-external-link-edit').isVisible()) throw new Error('viewer: barcode/externe-link-mutatie mag niet zichtbaar zijn')
  if (!(await page.locator('.rz-article-automation-select').isDisabled())) throw new Error('viewer: automatisering moet disabled zijn')
  if (writes.details.length || writes.settings.length || writes.automation.length || writes.externalLinks.length) {
    throw new Error(`viewer: onverwachte write ${JSON.stringify(writes)}`)
  }
  await page.close()
}

const browser = await chromium.launch({ headless: true })
try {
  await verifyMutableRole(browser, 'owner')
  await verifyMutableRole(browser, 'admin')
  await verifyViewer(browser)
  console.log('ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN')
} finally {
  await browser.close()
}
