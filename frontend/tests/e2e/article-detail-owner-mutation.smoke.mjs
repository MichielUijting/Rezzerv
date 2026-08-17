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

    if (path === '/api/session' || path === '/api/household') return json(sessionPayload(role))
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
  await page.locator('.rz-stock-summary-table-quantity').filter({ hasText: String(expected) }).first().waitFor({ state: 'visible' })
}

async function activateNativeSubtab(page, testId, label) {
  await page.waitForFunction((id) => {
    const element = document.querySelector(`[data-testid="${id}"]`)
    if (!element || element.disabled) return false
    const rect = element.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
  }, testId)

  const stability = await page.evaluate(async (id) => {
    const first = document.querySelector(`[data-testid="${id}"]`)
    await new Promise((resolve) => window.setTimeout(resolve, 150))
    const second = document.querySelector(`[data-testid="${id}"]`)
    return {
      exists: Boolean(first && second),
      sameNode: Boolean(first && second && first === second),
    }
  }, testId)

  if (!stability.exists) throw new Error(`${label}: subtab verdween uit de DOM`)
  if (!stability.sameNode) throw new Error(`${label}: subtab-node wordt continu vervangen tijdens renderen`)

  const clickResult = await page.evaluate(({ id, label: expectedLabel }) => {
    const element = document.querySelector(`[data-testid="${id}"]`)
    if (!element) return { ok: false, reason: 'missing' }
    const rect = element.getBoundingClientRect()
    const style = window.getComputedStyle(element)
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0 || rect.width <= 0 || rect.height <= 0) {
      return { ok: false, reason: 'not-visible', rect: { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, width: rect.width, height: rect.height } }
    }
    element.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    const nextRect = element.getBoundingClientRect()
    const x = Math.max(0, Math.min(window.innerWidth - 1, nextRect.left + nextRect.width / 2))
    const y = Math.max(0, Math.min(window.innerHeight - 1, nextRect.top + nextRect.height / 2))
    const hit = document.elementFromPoint(x, y)
    if (!hit || (hit !== element && !element.contains(hit))) {
      return { ok: false, reason: 'covered', hit: hit?.getAttribute?.('data-testid') || hit?.tagName || null }
    }
    if (String(element.textContent || '').trim() !== expectedLabel) {
      return { ok: false, reason: 'wrong-label', text: String(element.textContent || '').trim() }
    }
    element.click()
    return { ok: true }
  }, { id: testId, label })

  if (!clickResult.ok) throw new Error(`${label}: native subtab-click mislukt ${JSON.stringify(clickResult)}`)

  await page.waitForFunction((id) => {
    const element = document.querySelector(`[data-testid="${id}"]`)
    return Boolean(element && element.getAttribute('aria-selected') === 'true')
  }, testId)
}

const OVERVIEW_SUBTABS = [
  ['article-overview-subtab-article', 'Artikel', 'article-household-details-section'],
  ['article-overview-subtab-household', 'Huishouden', 'article-household-settings-section'],
  ['article-overview-subtab-identity', 'Identiteit', 'article-external-link-section'],
  ['article-overview-subtab-productdata', 'Productdata', 'article-product-enrichment-section'],
]

async function verifyOverviewSubtabs(page) {
  for (const [testId, label, sectionTestId] of OVERVIEW_SUBTABS) {
    await activateNativeSubtab(page, testId, label)
    await page.getByTestId(sectionTestId).waitFor({ state: 'visible' })
  }
  await activateNativeSubtab(page, 'article-overview-subtab-article', 'Artikel')
}

async function verifyAnalysisSubtabs(page) {
  await page.getByRole('tab', { name: 'Analyse', exact: true }).click()

  const cases = [
    ['article-analysis-subtab-trends', 'Trends', 'Aankoop en verbruik in de tijd'],
    ['article-analysis-subtab-price', 'Prijs', 'Prijsinzichten'],
    ['article-analysis-subtab-forecast', 'Prognose', 'Voorraadprognose'],
    ['article-analysis-subtab-evidence', 'Onderbouwing', 'Onderbouwing'],
  ]

  for (const [testId, label, content] of cases) {
    await activateNativeSubtab(page, testId, label)
    await page.getByText(content, { exact: true }).waitFor({ state: 'visible' })
  }
}

async function verifyMutableRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, role)
  const consoleErrors = []
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()) })

  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  await verifyOverviewSubtabs(page)

  const ownName = page.getByTestId('article-details-input-custom_name')
  if (await ownName.isDisabled()) throw new Error(`${role}: Eigen naam is ten onrechte disabled`)
  await ownName.fill(`PO ${role.toUpperCase()} SMOKE`)
  const patchResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}` && response.request().method() === 'PATCH')
  await ownName.blur()
  if (!(await patchResponsePromise).ok()) throw new Error(`${role}: PATCH faalde`)

  await activateNativeSubtab(page, 'article-overview-subtab-household', 'Huishouden')
  const settingsSave = page.getByTestId('article-household-settings-save')
  if (await settingsSave.isDisabled()) throw new Error(`${role}: huishoudinstellingen zijn ten onrechte disabled`)
  await page.getByTestId('article-details-input-notes').fill(`Notitie ${role}`)
  const settingsResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/settings` && response.request().method() === 'PUT')
  await settingsSave.click()
  if (!(await settingsResponsePromise).ok()) throw new Error(`${role}: settings PUT faalde`)

  const householdSubtab = await page.evaluate(() => document.querySelector('[data-testid="article-overview-subtab-household"]')?.getAttribute('aria-selected'))
  if (householdSubtab !== 'true') throw new Error(`${role}: Huishouden-subtab bleef niet geselecteerd na live refresh`)

  const automation = page.locator('.rz-article-automation-select')
  await automation.waitFor({ state: 'visible' })
  if (await automation.isDisabled()) throw new Error(`${role}: automatisering is ten onrechte disabled`)
  const beforeMode = await automation.inputValue()
  const nextMode = beforeMode === 'always_on' ? 'always_off' : 'always_on'
  const automationResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/automation-override` && response.request().method() === 'PUT')
  await automation.selectOption(nextMode)
  if (!(await automationResponsePromise).ok()) throw new Error(`${role}: automation PUT faalde`)

  await activateNativeSubtab(page, 'article-overview-subtab-identity', 'Identiteit')
  if (await page.getByTestId('article-external-link-edit').isVisible()) throw new Error(`${role}: barcode-mutatie is ten onrechte zichtbaar`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  const adjust = page.getByTestId(`article-stock-adjust-${articleId}`)
  const consume = page.getByTestId(`article-stock-consume-${articleId}`)
  if (await adjust.isDisabled()) throw new Error(`${role}: Corrigeren is ten onrechte disabled`)
  if (await consume.isDisabled()) throw new Error(`${role}: Afboeken is ten onrechte disabled`)

  await adjust.click()
  await page.getByLabel('Nieuwe hoeveelheid').fill('3')
  const adjustResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/inventory-events` && response.request().method() === 'POST')
  await page.getByTestId('article-stock-mutation-form').getByRole('button', { name: 'Opslaan' }).click()
  if (!(await adjustResponsePromise).ok()) throw new Error(`${role}: voorraadcorrectie faalde`)
  await waitForInventoryQuantity(page, 3)

  await consume.click()
  await page.getByLabel('Aantal afboeken').fill('1')
  const consumeResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === `/api/household-articles/${articleId}/inventory-events` && response.request().method() === 'POST')
  await page.getByTestId('article-stock-mutation-form').getByRole('button', { name: 'Opslaan' }).click()
  if (!(await consumeResponsePromise).ok()) throw new Error(`${role}: afboeking faalde`)
  await waitForInventoryQuantity(page, 2)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  if (await page.getByTestId('article-location-action-transfer').isDisabled()) throw new Error(`${role}: Verplaatsen is ten onrechte disabled`)

  await verifyAnalysisSubtabs(page)

  if (writes.details.length !== 1 || writes.details[0]?.custom_name !== `PO ${role.toUpperCase()} SMOKE`) throw new Error(`${role}: onjuiste detail-write ${JSON.stringify(writes.details)}`)
  if (writes.settings.length !== 1 || writes.settings[0]?.notes !== `Notitie ${role}`) throw new Error(`${role}: onjuiste settings-write ${JSON.stringify(writes.settings)}`)
  if (writes.automation.length !== 1 || writes.automation[0]?.mode !== nextMode) throw new Error(`${role}: onjuiste automation-write ${JSON.stringify(writes.automation)}`)
  if (writes.inventoryEvents.length !== 2) throw new Error(`${role}: verwacht 2 voorraadwrites ${JSON.stringify(writes.inventoryEvents)}`)
  if (writes.genericInventoryWrites.length) throw new Error(`${role}: generieke voorraadroute gebruikt ${JSON.stringify(writes.genericInventoryWrites)}`)
  if (writes.externalLinks.length) throw new Error(`${role}: onverwachte external-link-write ${JSON.stringify(writes.externalLinks)}`)
  if (consoleErrors.length) throw new Error(`${role}: console errors ${consoleErrors.join(' | ')}`)

  await page.close()
}

async function verifyReadOnlyRole(browser, role) {
  const page = await browser.newPage()
  const writes = await installApiMocks(page, role)
  await page.goto(`${baseURL}/voorraad/${articleId}`, { waitUntil: 'networkidle' })
  await verifyOverviewSubtabs(page)

  await activateNativeSubtab(page, 'article-overview-subtab-article', 'Artikel')
  if (!(await page.getByTestId('article-details-input-custom_name').isDisabled())) throw new Error(`${role}: Eigen naam moet read-only zijn`)

  await activateNativeSubtab(page, 'article-overview-subtab-household', 'Huishouden')
  if (!(await page.getByTestId('article-household-settings-save').isDisabled())) throw new Error(`${role}: instellingen moeten read-only zijn`)
  if (!(await page.locator('.rz-article-automation-select').isDisabled())) throw new Error(`${role}: automatisering moet read-only zijn`)

  await page.getByRole('tab', { name: 'Voorraad', exact: true }).click()
  if (!(await page.getByTestId(`article-stock-adjust-${articleId}`).isDisabled())) throw new Error(`${role}: Corrigeren moet disabled zijn`)
  if (!(await page.getByTestId(`article-stock-consume-${articleId}`).isDisabled())) throw new Error(`${role}: Afboeken moet disabled zijn`)

  await page.getByRole('tab', { name: 'Locaties', exact: true }).click()
  if (!(await page.getByTestId('article-location-action-transfer').isDisabled())) throw new Error(`${role}: Verplaatsen moet disabled zijn`)

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
