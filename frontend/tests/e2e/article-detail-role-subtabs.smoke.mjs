import { chromium } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174'
const articleId = 'article-role-subtabs-smoke'
const articleName = '7 Granen Ontbijt'

function sessionPayload(role) {
  const admin = role === 'owner' || role === 'admin'
  const member = role === 'member'
  return {
    user_id: `${role}-user`,
    email: `${role}@rezzerv.test`,
    active_household_id: '1',
    active_household_name: 'Smoke huishouden',
    role,
    display_role: role,
    membership_count: 1,
    can_switch_households: false,
    permissions: admin
      ? { 'admin.access': true, 'inventory.update': true, 'inventory.correct': true }
      : member
        ? { 'inventory.update': true, 'inventory.correct': true }
        : {},
    is_viewer: role === 'viewer',
  }
}

async function installMocks(page, role) {
  let customName = 'Oude naam'
  let inventoryQuantity = 2
  let automationMode = 'follow_household'
  let settings = {
    min_stock: 1,
    ideal_stock: 2,
    favorite_store: 'ALDI',
    average_price: 2.49,
    status: 'active',
    default_location_id: null,
    default_sublocation_id: null,
    auto_restock: false,
    packaging_unit: 'pak',
    packaging_quantity: 1,
    notes: '',
  }
  const writes = { details: [], settings: [], automation: [], inventory: [], transfer: [], generic: [], external: [] }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const reply = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (path === '/api/session' || path === '/api/household') return reply(sessionPayload(role))
    if (path === '/api/settings/article-field-visibility') {
      return reply({ overview: { article_name: true, custom_name: true, article_type: true, category: true, brand_or_maker: true, barcode: true, article_number: true, notes: true, calories: true }, stock: {}, locations: {}, history: {}, analytics: {} })
    }
    if (path === '/api/dev/inventory-preview') {
      return reply({ rows: [{ id: articleId, household_article_id: articleId, artikel: articleName, aantal: inventoryQuantity, space_id: 'space-1', sublocation_id: 'sub-1', locatie: 'Voorraadkast', sublocatie: 'Plank 1' }] })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'GET') {
      return reply({
        id: articleId,
        article_id: articleId,
        household_article_id: articleId,
        article_name: articleName,
        name: articleName,
        custom_name: customName,
        article_type: 'Voedsel & drank',
        category: 'Ontbijtgranen',
        brand_or_maker: 'ALDI',
        total_quantity: inventoryQuantity,
        barcode: '8712345678901',
        article_number: 'EXT-123',
        source: 'internal_catalog',
        settings,
        locations: [{ id: articleId, space_id: 'space-1', sublocation_id: 'sub-1', locatie: 'Voorraadkast', sublocatie: 'Plank 1', aantal: inventoryQuantity }],
        product_details: {
          identity: { normalized_barcode: '8712345678901', source: 'internal_catalog', confidence_score: 0.99 },
          internal_catalog: { global_product_id: 'technical-id-not-for-user', status: 'found' },
          source_chain: [{ source_name: 'internal_catalog', configured: true, enabled: true }],
          enrichment_status: { status: 'found', last_lookup_message: 'technical lookup message' },
          enrichment: {
            title: '7 Granen Ontbijt',
            brand: 'ALDI',
            category: 'Ontbijtgranen',
            size_value: 500,
            size_unit: 'g',
            ingredients: ['haver', 'tarwe'],
            allergens: ['gluten'],
            source_name: 'open_food_facts',
          },
        },
      })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'PATCH') {
      const body = request.postDataJSON()
      writes.details.push(body)
      customName = String(body?.custom_name || '')
      return reply({ details: { article_id: articleId, household_article_id: articleId, article_name: articleName, name: articleName, custom_name: customName, article_type: 'Voedsel & drank', settings } })
    }
    if (path === `/api/household-articles/${articleId}/settings` && method === 'PUT') {
      const body = request.postDataJSON()
      writes.settings.push(body)
      settings = { ...settings, ...body }
      return reply({ settings })
    }
    if (path === `/api/household-articles/${articleId}/events`) return reply({ items: [] })
    if (path === `/api/household-articles/${articleId}/automation-override` && method === 'GET') {
      return reply({ article_id: articleId, household_article_id: articleId, mode: automationMode, has_explicit_override: automationMode !== 'follow_household', consumable: true })
    }
    if (path === `/api/household-articles/${articleId}/automation-override` && method === 'PUT') {
      const body = request.postDataJSON()
      writes.automation.push(body)
      automationMode = String(body?.mode || 'follow_household')
      return reply({ article_id: articleId, household_article_id: articleId, mode: automationMode, has_explicit_override: true, consumable: true })
    }
    if (path === `/api/household-articles/${articleId}/inventory-events` && method === 'POST') {
      const body = request.postDataJSON()
      writes.inventory.push(body)
      if (body.event_type === 'adjustment') inventoryQuantity = Number(body.quantity)
      if (body.event_type === 'consume') inventoryQuantity = Math.max(0, inventoryQuantity - Number(body.quantity || 0))
      return reply({ status: 'ok', article_total_quantity: inventoryQuantity, row_new_quantity: inventoryQuantity })
    }
    if (path === `/api/household-articles/${articleId}/inventory-transfers` && method === 'POST') {
      writes.transfer.push(request.postDataJSON())
      return reply({ status: 'ok' })
    }
    if ((path === '/api/inventory-events' || path === '/api/inventory-transfers') && method === 'POST') {
      writes.generic.push({ path, body: request.postDataJSON() })
      return reply({ detail: 'Generieke voorraadwrite vanaf Artikeldetail is verboden' }, 500)
    }
    if (path === '/api/spaces') return reply({ items: [{ id: 'space-1', naam: 'Voorraadkast', active: true }, { id: 'space-2', naam: 'Keuken', active: true }] })
    if (path === '/api/sublocations') return reply({ items: [{ id: 'sub-1', space_id: 'space-1', naam: 'Plank 1', active: true }, { id: 'sub-2', space_id: 'space-2', naam: 'Kast', active: true }] })
    if (path.includes('/external-product-link')) {
      writes.external.push(request.postDataJSON())
      return reply({})
    }
    return reply({})
  })

  return writes
}

async function activateSubtab(page, testId, expectedKey, expectedVisibleSelector) {
  await page.waitForFunction((id) => {
    const element = document.querySelector(`[data-testid="${id}"]`)
    if (!element || element.disabled) return false
    element.click()
    return true
  }, testId)

  await page.waitForFunction(({ id, key, selector }) => {
    const tab = document.querySelector(`[data-testid="${id}"]`)
    const layout = tab?.closest('.rz-article-subtab-layout')
    const target = document.querySelector(selector)
    if (!tab || !layout || !target) return false
    const targetStyle = window.getComputedStyle(target)
    return tab.getAttribute('aria-selected') === 'true' && layout.dataset.activeSubtab === key && targetStyle.display !== 'none' && targetStyle.visibility !== 'hidden'
  }, { id: testId, key: expectedKey, selector: expectedVisibleSelector })
}

async function verifyOverviewSubtabs(page) {
  await activateSubtab(page, 'article-overview-subtab-article', 'article', '[data-testid="article-household-details-section"]')
  await page.getByTestId('article-household-name-help').waitFor({ state: 'visible' })

  await activateSubtab(page, 'article-overview-subtab-household', 'household', '[data-testid="article-household-settings-section"]')
  await page.getByTestId('article-household-settings-help').waitFor({ state: 'visible' })

  await activateSubtab(page, 'article-overview-subtab-identity', 'identity', '[data-testid="article-identity-summary"]')
  const identitySummary = page.getByTestId('article-identity-summary')
  await identitySummary.getByText('8712345678901', { exact: true }).waitFor({ state: 'visible' })
  await identitySummary.getByText('EXT-123', { exact: true }).waitFor({ state: 'visible' })
  if (await page.getByTestId('article-external-link-section').isVisible()) throw new Error('Legacy externe productkoppeling is nog zichtbaar')

  await activateSubtab(page, 'article-overview-subtab-productdata', 'productdata', '[data-testid="article-product-summary"]')
  const productSummary = page.getByTestId('article-product-summary')
  for (const text of ['7 Granen Ontbijt', 'ALDI', 'Ontbijtgranen', '500 g', 'haver, tarwe', 'gluten', 'Open Food Facts']) {
    await productSummary.getByText(text, { exact: true }).waitFor({ state: 'visible' })
  }
  if (await page.getByTestId('article-product-enrichment-section').isVisible()) throw new Error('Legacy Productverrijking is nog zichtbaar')
  for (const technicalText of ['Bronketen', 'Interne matchstatus', 'Centrale product-ID', 'Confidence', 'Lookup melding']) {
    if (await page.getByText(technicalText, { exact: false }).isVisible()) throw new Error(`Technische ballast is zichtbaar: ${technicalText}`)
  }

  await activateSubtab(page, 'article-overview-subtab-article', 'article', '[data-testid="article-household-details-section"]')
}

async function verifyAnalysisSubtabs(page) {
  await page.getByRole('tab', { name: 'Analyse', exact: true }).click()
  await page.getByTestId('article-analysis-subtabs').waitFor({ state: 'visible' })
  await activateSubtab(page, 'article-analysis-subtab-trends', 'trends', '[data-testid="analysis-row-consumption"]')
  await activateSubtab(page, 'article-analysis-subtab-price', 'price', '[data-testid="analysis-row-price"]')
  await activateSubtab(page, 'article-analysis-subtab-forecast', 'forecast', '[data-testid="analysis-row-forecast"]')
  await activateSubtab(page, 'article-analysis-subtab-evidence', 'evidence', '[data-testid="analysis-row-quality"]')
}

async function assertEditableBlack(page, selector, label) {
  const color = await page.locator(selector).evaluate((element) => window.getComputedStyle(element).color)
  if (color !== 'rgb(0, 0, 0)') throw new Error(`${label}: bewerkbare waarde is niet zwart (${color})`)
}

async function verifyAdminRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installMocks(page, role)
  const consoleErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })
  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })

  await verifyOverviewSubtabs(page)
  const ownName = page.getByTestId('article-details-input-custom_name')
  if (await ownName.isDisabled()) throw new Error(`${role}: Naam in dit huishouden is read-only`)
  await assertEditableBlack(page, '[data-testid="article-details-input-custom_name"]', `${role}: Naam in dit huishouden`)
  await ownName.fill(`PO ${role.toUpperCase()} SUBTABS`)
  const patch = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}` && response.request().method() === 'PATCH')
  await ownName.blur()
  if (!(await patch).ok()) throw new Error(`${role}: huishoudnaam PATCH faalde`)

  await activateSubtab(page, 'article-overview-subtab-household', 'household', '[data-testid="article-household-settings-section"]')
  const save = page.getByTestId('article-household-settings-save')
  if (await save.isDisabled()) throw new Error(`${role}: Instellingen zijn read-only`)
  if (await page.getByTestId('article-details-input-average_price').isVisible()) throw new Error(`${role}: afgeleide Prijsindicatie is nog handmatig zichtbaar`)
  if (await page.getByTestId('article-household-settings-auto-restock').isVisible()) throw new Error(`${role}: niet-functionele auto_restock is nog zichtbaar`)
  await assertEditableBlack(page, '[data-testid="article-details-input-notes"]', `${role}: Notities`)
  await page.getByTestId('article-details-input-notes').fill(`Notitie ${role}`)
  const settingsResponse = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/settings` && response.request().method() === 'PUT')
  await save.click()
  if (!(await settingsResponse).ok()) throw new Error(`${role}: instellingen PUT faalde`)
  await page.waitForFunction(() => document.querySelector('[data-testid="article-overview-subtab-household"]')?.getAttribute('aria-selected') === 'true' && window.sessionStorage.getItem('rezzerv.article-detail.overview-subtab') === 'Huishouden')

  const automation = page.locator('.rz-article-automation-select')
  await automation.waitFor({ state: 'visible' })
  if (await automation.isDisabled()) throw new Error(`${role}: Automatisering is read-only`)
  await assertEditableBlack(page, '.rz-article-automation-select', `${role}: Automatisering`)
  const currentMode = await automation.inputValue()
  const nextMode = currentMode === 'always_on' ? 'always_off' : 'always_on'
  const automationResponse = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/automation-override` && response.request().method() === 'PUT')
  await automation.selectOption(nextMode)
  if (!(await automationResponse).ok()) throw new Error(`${role}: automatisering PUT faalde`)

  await activateSubtab(page, 'article-overview-subtab-identity', 'identity', '[data-testid="article-identity-summary"]')
  if (await page.getByTestId('article-external-link-edit').isVisible()) throw new Error(`${role}: barcode-mutatie is zichtbaar`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjust = page.getByTestId(`article-stock-adjust-${articleId}`)
  const consume = page.getByTestId(`article-stock-consume-${articleId}`)
  if (await adjust.isDisabled() || await consume.isDisabled()) throw new Error(`${role}: voorraadbeheer is geblokkeerd`)
  await adjust.click()
  await page.getByLabel('Nieuwe hoeveelheid').fill('3')
  const adjustResponse = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/inventory-events` && response.request().method() === 'POST')
  await page.getByTestId('article-stock-mutation-form').getByRole('button', { name: 'Opslaan' }).click()
  if (!(await adjustResponse).ok()) throw new Error(`${role}: voorraadcorrectie faalde`)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  if (await page.getByTestId('article-location-action-transfer').isDisabled()) throw new Error(`${role}: Verplaatsen is geblokkeerd`)

  await verifyAnalysisSubtabs(page)

  if (writes.details.length !== 1 || writes.settings.length !== 1 || writes.automation.length !== 1 || writes.inventory.length !== 1) throw new Error(`${role}: verplichte writes ontbreken ${JSON.stringify(writes)}`)
  if (writes.generic.length || writes.external.length) throw new Error(`${role}: verboden write gebruikt ${JSON.stringify(writes)}`)
  if (consoleErrors.length) throw new Error(`${role}: console errors ${consoleErrors.join(' | ')}`)
  await page.close()
}

async function verifyReadOnlyRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installMocks(page, role)
  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })

  await verifyOverviewSubtabs(page)
  await activateSubtab(page, 'article-overview-subtab-article', 'article', '[data-testid="article-household-details-section"]')
  if (!(await page.getByTestId('article-details-input-custom_name').isDisabled())) throw new Error(`${role}: Naam in dit huishouden is muteerbaar`)

  await activateSubtab(page, 'article-overview-subtab-household', 'household', '[data-testid="article-household-settings-section"]')
  if (!(await page.getByTestId('article-household-settings-save').isDisabled())) throw new Error(`${role}: instellingen zijn muteerbaar`)
  if (!(await page.locator('.rz-article-automation-select').isDisabled())) throw new Error(`${role}: automatisering is muteerbaar`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  if (!(await page.getByTestId(`article-stock-adjust-${articleId}`).isDisabled())) throw new Error(`${role}: Corrigeren is muteerbaar`)
  if (!(await page.getByTestId(`article-stock-consume-${articleId}`).isDisabled())) throw new Error(`${role}: Afboeken is muteerbaar`)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  if (!(await page.getByTestId('article-location-action-transfer').isDisabled())) throw new Error(`${role}: Verplaatsen is muteerbaar`)

  await verifyAnalysisSubtabs(page)

  if (writes.details.length || writes.settings.length || writes.automation.length || writes.inventory.length || writes.transfer.length || writes.generic.length || writes.external.length) {
    throw new Error(`${role}: read-only rol veroorzaakte write ${JSON.stringify(writes)}`)
  }
  await page.close()
}

const browser = await chromium.launch({ headless: true })
try {
  await verifyAdminRole(browser, 'owner')
  await verifyAdminRole(browser, 'admin')
  await verifyReadOnlyRole(browser, 'member')
  await verifyReadOnlyRole(browser, 'viewer')
  console.log('ARTICLE_DETAIL_MEMBER_READONLY_BROWSER_GREEN')
  console.log('ARTICLE_DETAIL_SUBTABS_BROWSER_GREEN')
  console.log('ARTICLE_DETAIL_CURATED_OVERVIEW_BROWSER_GREEN')
  console.log('ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN')
} finally {
  await browser.close()
}
