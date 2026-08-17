import { chromium } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174'
const articleId = 'article-owner-smoke'
const articleName = '7 Granen Ontbijt'

function sessionPayload(role) {
  const mutable = role === 'owner' || role === 'admin'
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
    permissions: mutable
      ? { 'admin.access': true, 'inventory.update': true, 'inventory.correct': true }
      : member
        ? { 'inventory.update': true, 'inventory.correct': true }
        : {},
    is_viewer: role === 'viewer',
  }
}

async function installApiMocks(page, role) {
  let customName = 'Oude naam'
  let inventoryQuantity = 2
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
    inventoryEvents: [],
    inventoryTransfers: [],
    externalLinks: [],
    genericInventoryWrites: [],
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
      return json({
        overview: {
          article_name: true,
          custom_name: true,
          article_type: true,
          barcode: true,
          article_number: true,
          notes: true,
          calories: true,
        },
        stock: {}, locations: {}, history: {}, analytics: {},
      })
    }
    if (path === '/api/dev/inventory-preview') {
      return json({ rows: [{ id: articleId, household_article_id: articleId, artikel: articleName, aantal: inventoryQuantity, space_id: 'space-1', sublocation_id: 'sub-1', locatie: 'Voorraadkast', sublocatie: 'Plank 1' }] })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'GET') {
      return json({
        id: articleId,
        article_id: articleId,
        household_article_id: articleId,
        article_name: articleName,
        name: articleName,
        custom_name: customName,
        article_type: 'Voedsel & drank',
        total_quantity: inventoryQuantity,
        barcode: '8712345678901',
        article_number: 'EXT-123',
        settings,
        product_details: { identity: {}, internal_catalog: {}, source_chain: [] },
      })
    }
    if (path === `/api/household-articles/${articleId}` && method === 'PATCH') {
      const body = request.postDataJSON()
      writes.details.push(body)
      customName = String(body?.custom_name || '')
      return json({ details: { article_id: articleId, household_article_id: articleId, article_name: articleName, name: articleName, custom_name: customName, article_type: 'Voedsel & drank', barcode: '8712345678901', article_number: 'EXT-123', settings } })
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
    if (path === `/api/household-articles/${articleId}/inventory-events` && method === 'POST') {
      const body = request.postDataJSON()
      writes.inventoryEvents.push(body)
      if (body?.event_type === 'adjustment') inventoryQuantity = Number(body.quantity)
      if (body?.event_type === 'consume') inventoryQuantity = Math.max(0, inventoryQuantity - Number(body.quantity || 0))
      return json({ status: 'ok', article_total_quantity: inventoryQuantity, row_new_quantity: inventoryQuantity })
    }
    if (path === `/api/household-articles/${articleId}/inventory-transfers` && method === 'POST') {
      writes.inventoryTransfers.push(request.postDataJSON())
      return json({ status: 'ok' })
    }
    if ((path === '/api/inventory-events' || path === '/api/inventory-transfers') && method === 'POST') {
      writes.genericInventoryWrites.push({ path, body: request.postDataJSON() })
      return json({ detail: 'Artikeldetail mag geen generieke write-route gebruiken' }, 500)
    }
    if (path === '/api/spaces') return json({ items: [{ id: 'space-1', naam: 'Voorraadkast', active: true }, { id: 'space-2', naam: 'Keuken', active: true }] })
    if (path === '/api/sublocations') return json({ items: [{ id: 'sub-1', space_id: 'space-1', naam: 'Plank 1', active: true }, { id: 'sub-2', space_id: 'space-2', naam: 'Kast', active: true }] })
    if (path.includes('/external-product-link')) {
      writes.externalLinks.push(request.postDataJSON())
      return json({})
    }
    return json({})
  })
  return writes
}

async function waitForInventoryQuantity(page, expected) {
  const quantity = page.locator('.rz-stock-summary-table-quantity').filter({ hasText: String(expected) }).first()
  await quantity.waitFor({ state: 'visible' })
}

async function verifyOverviewSubtabs(page) {
  const tabs = ['Artikel', 'Huishouden', 'Identiteit', 'Productdata']
  for (const name of tabs) {
    const tab = page.getByRole('tab', { name, exact: true })
    await tab.waitFor({ state: 'visible' })
  }

  await page.getByRole('tab', { name: 'Artikel', exact: true }).click()
  await page.getByTestId('article-household-details-section').waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Huishouden', exact: true }).click()
  await page.getByTestId('article-household-settings-section').waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Identiteit', exact: true }).click()
  await page.getByTestId('article-external-link-section').waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Productdata', exact: true }).click()
  await page.getByTestId('article-product-enrichment-section').waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Artikel', exact: true }).click()
}

async function verifyAnalysisSubtabs(page) {
  await page.getByRole('tab', { name: 'Analyse', exact: true }).click()
  for (const name of ['Trends', 'Prijs', 'Prognose', 'Onderbouwing']) {
    await page.getByRole('tab', { name, exact: true }).waitFor({ state: 'visible' })
  }

  await page.getByRole('tab', { name: 'Trends', exact: true }).click()
  await page.getByText('Aankoop en verbruik in de tijd', { exact: true }).waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Prijs', exact: true }).click()
  await page.getByText('Prijsinzichten', { exact: true }).waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Prognose', exact: true }).click()
  await page.getByText('Voorraadprognose', { exact: true }).waitFor({ state: 'visible' })
  await page.getByRole('tab', { name: 'Onderbouwing', exact: true }).click()
  await page.getByText('Onderbouwing', { exact: true }).waitFor({ state: 'visible' })
}

async function verifyMutableRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, role)
  const consoleErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  await verifyOverviewSubtabs(page)

  const ownName = page.getByTestId('article-details-input-custom_name')
  await ownName.waitFor({ state: 'visible' })
  if (await ownName.isDisabled()) throw new Error(`${role}: Eigen naam is ten onrechte disabled`)

  await ownName.fill(`PO ${role.toUpperCase()} SMOKE`)
  const patchResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}` && response.request().method() === 'PATCH'
  })
  await ownName.blur()
  const patchResponse = await patchResponsePromise
  if (!patchResponse.ok()) throw new Error(`${role}: PATCH gaf HTTP ${patchResponse.status()}`)

  await page.getByRole('tab', { name: 'Huishouden', exact: true }).click()
  const settingsSave = page.getByTestId('article-household-settings-save')
  await settingsSave.waitFor({ state: 'visible' })
  if (await settingsSave.isDisabled()) throw new Error(`${role}: huishoudinstellingen zijn ten onrechte disabled`)

  const notes = page.getByTestId('article-details-input-notes')
  await notes.fill(`Notitie ${role}`)
  const settingsResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/settings` && response.request().method() === 'PUT'
  })
  await settingsSave.click()
  const settingsResponse = await settingsResponsePromise
  if (!settingsResponse.ok()) throw new Error(`${role}: settings PUT gaf HTTP ${settingsResponse.status()}`)

  const automation = page.locator('.rz-article-automation-select')
  await automation.waitFor({ state: 'visible' })
  if (await automation.isDisabled()) throw new Error(`${role}: automatisering is ten onrechte disabled`)
  const automationBefore = await automation.inputValue()
  const nextAutomationMode = automationBefore === 'always_on' ? 'always_off' : 'always_on'
  const automationResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/automation-override` && response.request().method() === 'PUT'
  })
  await automation.selectOption(nextAutomationMode)
  const automationResponse = await automationResponsePromise
  if (!automationResponse.ok()) throw new Error(`${role}: automation PUT gaf HTTP ${automationResponse.status()}`)

  await page.getByRole('tab', { name: 'Identiteit', exact: true }).click()
  if (await page.getByTestId('article-external-link-edit').isVisible()) throw new Error(`${role}: barcode/externe-link-mutatie mag niet zichtbaar zijn op Artikeldetail`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjustButton = page.getByTestId(`article-stock-adjust-${articleId}`)
  const consumeButton = page.getByTestId(`article-stock-consume-${articleId}`)
  await adjustButton.waitFor({ state: 'visible' })
  if (await adjustButton.isDisabled()) throw new Error(`${role}: voorraad corrigeren is ten onrechte disabled`)
  if (await consumeButton.isDisabled()) throw new Error(`${role}: voorraad afboeken is ten onrechte disabled`)

  await adjustButton.click()
  await page.getByLabel('Nieuwe hoeveelheid').fill('3')
  await page.getByLabel('Reden / notitie').fill(`Correctie ${role}`)
  const adjustResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/inventory-events` && response.request().method() === 'POST'
  })
  await page.getByTestId('article-stock-mutation-form').getByRole('button', { name: 'Opslaan' }).click()
  const adjustResponse = await adjustResponsePromise
  if (!adjustResponse.ok()) throw new Error(`${role}: voorraadcorrectie gaf HTTP ${adjustResponse.status()}`)
  await waitForInventoryQuantity(page, 3)

  await consumeButton.click()
  await page.getByLabel('Aantal afboeken').fill('1')
  await page.getByLabel('Reden / notitie').fill(`Afboeking ${role}`)
  const consumeResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url())
    return url.pathname === `/api/household-articles/${articleId}/inventory-events` && response.request().method() === 'POST'
  })
  await page.getByTestId('article-stock-mutation-form').getByRole('button', { name: 'Opslaan' }).click()
  const consumeResponse = await consumeResponsePromise
  if (!consumeResponse.ok()) throw new Error(`${role}: afboeking gaf HTTP ${consumeResponse.status()}`)
  await waitForInventoryQuantity(page, 2)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  const transferButton = page.getByTestId('article-location-action-transfer')
  await transferButton.waitFor({ state: 'visible' })
  if (await transferButton.isDisabled()) throw new Error(`${role}: Verplaatsen is ten onrechte disabled`)

  await verifyAnalysisSubtabs(page)

  if (writes.details.length !== 1 || writes.details[0]?.custom_name !== `PO ${role.toUpperCase()} SMOKE` || Object.keys(writes.details[0]).length !== 1) {
    throw new Error(`${role}: onjuist PATCH-contract ${JSON.stringify(writes.details)}`)
  }
  if (writes.settings.length !== 1 || writes.settings[0]?.notes !== `Notitie ${role}`) {
    throw new Error(`${role}: huishoudinstellingen zijn niet werkelijk geschreven ${JSON.stringify(writes.settings)}`)
  }
  if (writes.automation.length !== 1 || writes.automation[0]?.mode !== nextAutomationMode || writes.automation[0]?.mode === automationBefore) {
    throw new Error(`${role}: automatisering is niet werkelijk naar een andere waarde geschreven ${JSON.stringify(writes.automation)}`)
  }
  if (writes.inventoryEvents.length !== 2) {
    throw new Error(`${role}: verwacht twee beheerste voorraadmutaties, gevonden ${JSON.stringify(writes.inventoryEvents)}`)
  }
  const [adjustWrite, consumeWrite] = writes.inventoryEvents
  if (adjustWrite?.event_type !== 'adjustment' || adjustWrite?.inventory_id !== articleId || adjustWrite?.quantity !== 3) {
    throw new Error(`${role}: onjuiste voorraadcorrectie ${JSON.stringify(adjustWrite)}`)
  }
  if (consumeWrite?.event_type !== 'consume' || consumeWrite?.inventory_id !== articleId || consumeWrite?.quantity !== 1) {
    throw new Error(`${role}: onjuiste afboeking ${JSON.stringify(consumeWrite)}`)
  }
  if (writes.genericInventoryWrites.length) throw new Error(`${role}: Artikeldetail gebruikte generieke voorraadroute ${JSON.stringify(writes.genericInventoryWrites)}`)
  if (writes.externalLinks.length) throw new Error(`${role}: onverwachte externe-productmutatie ${JSON.stringify(writes.externalLinks)}`)
  if (consoleErrors.length) throw new Error(`${role}: console errors: ${consoleErrors.join(' | ')}`)
  await page.close()
}

async function verifyReadOnlyRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, role)
  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  await verifyOverviewSubtabs(page)

  await page.getByRole('tab', { name: 'Artikel', exact: true }).click()
  const ownName = page.getByTestId('article-details-input-custom_name')
  await ownName.waitFor({ state: 'visible' })
  if (!(await ownName.isDisabled())) throw new Error(`${role}: Eigen naam moet read-only zijn`)

  await page.getByRole('tab', { name: 'Huishouden', exact: true }).click()
  const settingsSave = page.getByTestId('article-household-settings-save')
  await settingsSave.waitFor({ state: 'visible' })
  if (!(await settingsSave.isDisabled())) throw new Error(`${role}: huishoudinstellingen moeten read-only zijn`)
  if (!(await page.locator('.rz-article-automation-select').isDisabled())) throw new Error(`${role}: automatisering moet read-only zijn`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjustButton = page.getByTestId(`article-stock-adjust-${articleId}`)
  const consumeButton = page.getByTestId(`article-stock-consume-${articleId}`)
  await adjustButton.waitFor({ state: 'visible' })
  if (!(await adjustButton.isDisabled())) throw new Error(`${role}: voorraad corrigeren moet disabled zijn`)
  if (!(await consumeButton.isDisabled())) throw new Error(`${role}: voorraad afboeken moet disabled zijn`)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  const transferButton = page.getByTestId('article-location-action-transfer')
  await transferButton.waitFor({ state: 'visible' })
  if (!(await transferButton.isDisabled())) throw new Error(`${role}: Verplaatsen moet disabled zijn`)

  await verifyAnalysisSubtabs(page)

  if (writes.details.length || writes.settings.length || writes.automation.length || writes.inventoryEvents.length || writes.inventoryTransfers.length || writes.externalLinks.length || writes.genericInventoryWrites.length) {
    throw new Error(`${role}: onverwachte write ${JSON.stringify(writes)}`)
  }
  await page.close()
}

const browser = await chromium.launch({ headless: true })
try {
  await verifyMutableRole(browser, 'owner')
  await verifyMutableRole(browser, 'admin')
  await verifyReadOnlyRole(browser, 'member')
  await verifyReadOnlyRole(browser, 'viewer')
  console.log('ARTICLE_DETAIL_MEMBER_READONLY_BROWSER_GREEN')
  console.log('ARTICLE_DETAIL_SUBTABS_BROWSER_GREEN')
  console.log('ARTICLE_DETAIL_OWNER_MUTATION_BROWSER_GREEN')
} finally {
  await browser.close()
}
