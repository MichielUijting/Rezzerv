import { test, expect } from '@playwright/test'

const identity = {
  conflict_count: 2,
  source_rows_examined: 7,
  articles_examined: 3,
  complete: true,
  data_changed: false,
  products: [{ id: 'product-1', name: 'Halfvolle melk', primary_gtin: '8712345678906' }],
  items: [{
    household_article_id: 'article-a',
    article_name: 'Melk halfvol',
    reason: 'meerdere_huishoudartikelen',
    current_product_ids: [],
    candidate_product_ids: ['product-1'],
    source_count: 4,
    related_household_articles: [{ household_article_id: 'article-b', article_name: 'Melk uit andere boodschappen' }],
    sources: [
      { receipt_line_id: 'line-1', retailer_code: 'lidl', receipt_text: 'melk halfvol',
        external_article_code: '0012345', receipt_count: 2,
        identity_status: 'matched', candidate_product_id: 'product-1' },
      { receipt_line_id: 'line-2', retailer_code: 'lidl', receipt_text: 'melk halfvol',
        external_article_code: '0087654', receipt_count: 2,
        identity_status: 'matched', candidate_product_id: 'product-1' },
    ],
  }, {
    household_article_id: 'article-b', article_name: 'Melk uit andere boodschappen',
    reason: 'meerdere_huishoudartikelen',
    current_product_ids: [], candidate_product_ids: ['product-1'],
    source_count: 3,
    related_household_articles: [{ household_article_id: 'article-a', article_name: 'Melk halfvol' }],
    sources: [{ receipt_line_id: 'line-3', retailer_code: 'lidl',
      receipt_text: 'melk halfvol', external_article_code: '0012345',
      receipt_count: 3, identity_status: 'matched', candidate_product_id: 'product-1' }],
  }],
}

async function mockCatalog(page, { canReview = true, failSave = false, ordinaryAdmin = false, memberWithPlatformPermission = false } = {}) {
  let captured = null
  await page.route('**/api/session', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      user_id: 'test-owner', active_household_id: '1', context_type: 'regular',
      role: canReview ? 'owner' : 'viewer', display_role: canReview ? 'admin' : 'viewer',
      permissions: {
        'platform.external_products.link_existing': (canReview && !ordinaryAdmin) || memberWithPlatformPermission,
        'admin.access': canReview,
      },
      is_platform_superuser: false,
      is_frontteam: canReview && !ordinaryAdmin,
    }),
  }))
  // Regular household sessions must complete the real AuthGuard onboarding
  // preflight. Without this mock the guard redirects to Login.
  await page.route('**/api/onboarding', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ can_manage: true, initial_choice_required: false,
      onboarding_status: 'completed' }),
  }))
  await page.route('**/api/catalog?*', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ total: 0, items: [] }),
  }))
  await page.route('**/api/catalog/household-identity-conflicts', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify(identity),
  }))
  await page.route('**/api/catalog/household-identity-conflicts/confirm-source', async route => {
    captured = route.request().postDataJSON()
    await route.fulfill({
      status: failSave ? 409 : 200, contentType: 'application/json',
      body: JSON.stringify(failSave
        ? { detail: 'De broncode heeft al een andere Cataloguskoppeling.' }
        : { status: 'confirmed', changed: true,
          household_article_changes: 0, stock_changes: 0, receipt_changes: 0 }),
    })
  })
  return () => captured
}

test('Frontteambeheerder kan meerdere bonartikelnummers voor dezelfde omschrijving afzonderlijk bevestigen', async ({ page }) => {
  const getCaptured = await mockCatalog(page)
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  await expect(page.getByTestId('catalog-conflict-count')).toContainText('2')
  await expect(page.getByTestId('catalog-table')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Historische beoordeling sluiten' })).toHaveCount(0)
  await expect(page.getByTestId('catalog-conflicts-table').locator('thead tr.rz-table-filters')).toHaveCount(1)
  await expect(page.getByTestId('catalog-conflicts-table').locator('tbody button')).toHaveCount(0)
  await page.getByTestId('catalog-conflicts-table').getByRole('checkbox', { name: 'Selecteer huishoudartikel Melk halfvol' }).check()
  await page.getByRole('button', { name: 'Bonregels beoordelen (1)' }).click()
  const evidence = page.getByTestId('catalog-conflict-sources-table')
  await expect(page.getByTestId('catalog-conflict-explanation').first()).toContainText('Melk uit andere boodschappen')
  await expect(evidence.locator('tbody button')).toHaveCount(0)
  await expect(evidence.getByText('0012345')).toBeVisible()
  await expect(evidence.getByText('0087654')).toBeVisible()
  await evidence.getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0087654' }).check()
  await page.getByRole('button', { name: 'Barcode bepalen (1)' }).click()
  const dialog = page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })
  await dialog.getByLabel('Juiste Artikel-/barcode').fill('8712345678906')
  await dialog.getByRole('button', { name: 'Barcode bevestigen' }).click()
  await expect.poll(() => getCaptured()?.external_article_code).toBe('0087654')
  expect(getCaptured()).toEqual({
    household_article_id: 'article-a', receipt_line_id: 'line-2',
    retailer_code: 'lidl', receipt_text: 'melk halfvol',
    external_article_code: '0087654', target_gtin: '8712345678906',
  })
})

test('Mobiel blijft een conflicterende bron veilig zichtbaar na HTTP 409', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockCatalog(page, { failSave: true })
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  await page.getByTestId('catalog-conflicts-table').getByRole('checkbox', { name: 'Selecteer huishoudartikel Melk halfvol' }).check()
  await page.getByRole('button', { name: 'Bonregels beoordelen (1)' }).click()
  await page.getByTestId('catalog-conflict-sources-table').getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0012345' }).check()
  await page.getByRole('button', { name: 'Barcode bepalen (1)' }).click()
  const dialog = page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })
  await dialog.getByLabel('Juiste Artikel-/barcode').fill('8712345678906')
  await dialog.getByRole('button', { name: 'Barcode bevestigen' }).click()
  await expect(page.getByText('De broncode heeft al een andere Cataloguskoppeling.')).toBeVisible()
  await expect(dialog).toBeVisible()
  await expect(page.getByTestId('catalog-conflict-sources-table').getByText('0012345')).toBeVisible()
})

test('Zonder rechten is beoordeling niet beschikbaar', async ({ page }) => {
  await mockCatalog(page, { canReview: false })
  await page.goto('/catalogus')
  await expect(page.getByRole('button', { name: 'Historische conflicten beoordelen' })).toHaveCount(0)
})


async function mockSystemCatalog(page) {
  let householdReviewRequests = 0
  await page.route('**/api/session', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      user_id: 'system-editor', active_household_id: '0',
      context_type: 'system', role: 'superuser', display_role: 'superuser',
      is_platform_superuser: true,
      permissions: { 'platform.external_products.link_existing': true },
    }),
  }))
  await page.route('**/api/catalog?*', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ total: 0, items: [] }),
  }))
  await page.route('**/api/catalog/household-identity-conflicts', route => {
    householdReviewRequests += 1
    return route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        conflict_count: 0, source_rows_examined: 0, articles_examined: 0,
        complete: true, data_changed: false, items: [], products: [],
      }),
    })
  })
  return () => householdReviewRequests
}

for (const [name, width, height] of [
  ['desktop', 1280, 800],
  ['mobiel', 390, 844],
]) {
  test(`Superuser beoordeelt op ${name} uitsluitend Systeemhuishouden`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    const getReviewRequests = await mockSystemCatalog(page)
    await page.goto('/catalogus')
    const button = page.getByRole('button', { name: 'Historische conflicten beoordelen' })
    await expect(button).toBeVisible()
    await button.click()
    await expect(page.getByTestId('catalog-historical-conflicts')).toBeVisible()
    await expect(page.getByTestId('catalog-historical-conflicts')).toContainText('Systeemhuishouden')
    await expect(page.getByTestId('catalog-conflict-count')).toContainText('0')
    expect(getReviewRequests()).toBe(1)
    await expect(page.getByTestId('catalog-conflicts-table')).toHaveCount(0)
    const guidance = page.getByTestId('catalog-household-manager-guidance')
    await expect(guidance).toContainText('regulier account')
    await expect(guidance).toContainText('Beheerder')
    await expect(guidance).toContainText('Frontteamrol is hiervoor niet nodig')
    await expect(guidance.getByRole('button', { name: 'Naar Frontteambeheer' })).toHaveCount(0)
    expect(getReviewRequests()).toBe(1)
  })
}

for (const [name, width, height] of [
  ['desktop', 1280, 800],
  ['mobiel', 390, 844],
]) {
  test(`Gewone beheerder zonder platformrol kan eigen historische conflicten op ${name} bevestigen`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    const getCaptured = await mockCatalog(page, { ordinaryAdmin: true })
    await page.goto('/catalogus')
    await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
    await expect(page.getByTestId('catalog-conflict-count')).toContainText('2')
    await page.getByTestId('catalog-conflicts-table')
      .getByRole('checkbox', { name: 'Selecteer huishoudartikel Melk halfvol' }).check()
    await page.getByRole('button', { name: 'Bonregels beoordelen (1)' }).click()
    await page.getByTestId('catalog-conflict-sources-table')
      .getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0012345' }).check()
    await page.getByRole('button', { name: 'Barcode bepalen (1)' }).click()
    const dialog = page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })
    await dialog.getByLabel('Juiste Artikel-/barcode').fill('8712345678906')
    await dialog.getByRole('button', { name: 'Barcode bevestigen' }).click()
    await expect.poll(() => getCaptured()?.household_article_id).toBe('article-a')
    expect(getCaptured()?.receipt_line_id).toBe('line-1')
    expect(getCaptured()?.external_article_code).toBe('0012345')
  })

  test(`Gewoon lid met zelfs een platformpermissie ziet geen beoordeling op ${name}`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await mockCatalog(page, { canReview: false, memberWithPlatformPermission: true })
    await page.goto('/catalogus')
    await expect(page.getByRole('button', { name: 'Historische conflicten beoordelen' })).toHaveCount(0)
  })
}


test('Standaard DataTable filtert overzicht en bronregels zonder broncodes te wijzigen', async ({ page }) => {
  await mockCatalog(page, { ordinaryAdmin: true })
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  const conflicts = page.getByTestId('catalog-conflicts-table')
  await expect(conflicts.locator('thead tr.rz-table-filters')).toHaveCount(1)
  await expect(conflicts.locator('thead th')).toHaveCount(10)
  await conflicts.getByRole('textbox', { name: 'Filter op Huishoudartikel' }).fill('Melk halfvol')
  await expect(conflicts.locator('tbody tr')).toHaveCount(1)
  await expect(conflicts.getByText('Melk uit andere boodschappen')).toHaveCount(0)
  await conflicts.getByRole('textbox', { name: 'Filter op Huishoudartikel' }).fill('')

  await conflicts.getByRole('checkbox', { name: 'Selecteer huishoudartikel Melk halfvol' }).check()
  await page.getByRole('button', { name: 'Bonregels beoordelen (1)' }).click()
  const sources = page.getByTestId('catalog-conflict-sources-table')
  await expect(sources.locator('thead tr.rz-table-filters')).toHaveCount(1)
  await expect(sources.locator('thead th')).toHaveCount(14)
  await sources.getByRole('textbox', { name: 'Filter op Bonartikelnummer' }).fill('0087654')
  await expect(sources.locator('tbody tr')).toHaveCount(1)
  await expect(sources.getByText('0087654')).toBeVisible()
  await expect(sources.getByText('0012345')).toHaveCount(0)
  await sources.getByRole('textbox', { name: 'Filter op Bonartikelnummer' }).fill('')
  await expect(sources.locator('tbody tr')).toHaveCount(2)
})

test('Standaard DataTable pagineert tien conflicten en scrollbar staat onder de rijen', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 740 })
  await mockCatalog(page, { ordinaryAdmin: true })
  await page.route('**/api/catalog/household-identity-conflicts', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      ...identity,
      conflict_count: 13,
      items: Array.from({ length: 13 }, (_, index) => ({
        ...identity.items[0],
        household_article_id: `article-${String(index + 1).padStart(2, '0')}`,
        article_name: `Huishoudartikel ${String(index + 1).padStart(2, '0')}`,
      })),
    }),
  }))
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  const table = page.getByTestId('catalog-conflicts-table')
  const shell = page.locator('.rz-data-table-shell').filter({ has: table })
  await expect(table.locator('tbody tr')).toHaveCount(10)
  await expect(shell.locator('nav[aria-label="Paginering"]')).toBeVisible()
  const firstColumn = await table.locator('thead tr.rz-table-header th').nth(1).evaluate(element => ({
    width: element.getBoundingClientRect().width,
    alignment: getComputedStyle(element).textAlign,
  }))
  expect(firstColumn.width).toBeGreaterThanOrEqual(180)
  expect(firstColumn.alignment).toBe('left')
  const tableWrapper = shell.locator('.rz-table-wrapper')
  const scroll = await tableWrapper.evaluate(element => ({
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
    paddingBottom: getComputedStyle(element).paddingBottom,
  }))
  expect(scroll.scrollWidth).toBeGreaterThan(scroll.clientWidth)
  expect(Number.parseFloat(scroll.paddingBottom)).toBeGreaterThanOrEqual(24)
  await shell.getByRole('button', { name: '+' }).click()
  await expect(table.locator('tbody tr')).toHaveCount(3)
  await expect(table.getByText('Huishoudartikel 13')).toBeVisible()
  await expect(page.getByTestId('catalog-table')).toHaveCount(0)
})

test('Mobiele conflictenlijst gebruikt DataTable zonder de achterliggende Cataloguslijst', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockCatalog(page, { ordinaryAdmin: true })
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  const table = page.getByTestId('catalog-conflicts-table')
  await expect(table).toBeVisible()
  await expect(table.locator('thead tr.rz-table-filters')).toHaveCount(1)
  await expect(page.locator('.rz-mobile-catalog-toolbar')).toHaveCount(0)
  await expect(page.locator('.rz-mobile-catalog-list')).toHaveCount(0)
  await table.getByRole('checkbox', { name: 'Selecteer huishoudartikel Melk halfvol' }).check()
  await page.getByRole('button', { name: 'Bonregels beoordelen (1)' }).click()
  await expect(page.getByTestId('catalog-conflict-sources-table')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Terug naar Catalogus' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Historische beoordeling sluiten' })).toHaveCount(0)
  await page.goBack()
  await expect(page.getByTestId('catalog-conflicts-table')).toBeVisible()
  await page.goBack()
  await expect(page.locator('.rz-mobile-catalog-toolbar')).toBeVisible()
})


test('Bulkselectie toont samenhang tussen artikelen zonder ongevraagde barcodeverwerking', async ({ page }) => {
  const getCaptured = await mockCatalog(page, { ordinaryAdmin: true })
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  const conflicts = page.getByTestId('catalog-conflicts-table')
  await conflicts.getByRole('checkbox', { name: 'Alles: zichtbare huishoudartikelen' }).check()
  await expect(page.getByRole('button', { name: 'Bonregels beoordelen (2)' })).toBeEnabled()
  await expect(conflicts.locator('tbody button')).toHaveCount(0)
  await page.getByRole('button', { name: 'Bonregels beoordelen (2)' }).click()
  await expect(page).toHaveURL(/historischeConflicten=1/)
  await expect(page).toHaveURL(/artikelen=/)
  await expect(page.getByTestId('catalog-conflict-explanation')).toHaveCount(2)
  const sources = page.getByTestId('catalog-conflict-sources-table')
  await expect(sources.locator('tbody tr')).toHaveCount(3)
  await expect(sources.locator('tbody button')).toHaveCount(0)
  await sources.getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0087654' }).check()
  await sources.getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0012345' }).first().check()
  await page.getByRole('button', { name: 'Barcode bepalen (2)' }).click()
  await expect(page.getByText('Je hebt verschillende bonartikelcombinaties geselecteerd.')).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })).toHaveCount(0)
  expect(getCaptured()).toBeNull()

  await page.goBack()
  await expect(page.getByTestId('catalog-conflicts-table')).toBeVisible()
  await page.goBack()
  await expect(page.getByTestId('catalog-historical-conflicts')).toHaveCount(0)
})

test('Dezelfde bonartikelcombinatie mag uit meerdere geselecteerde bronregels veilig eenmaal worden bevestigd', async ({ page }) => {
  const getCaptured = await mockCatalog(page, { ordinaryAdmin: true })
  await page.goto('/catalogus')
  await page.getByRole('button', { name: 'Historische conflicten beoordelen' }).click()
  await page.getByTestId('catalog-conflicts-table')
    .getByRole('checkbox', { name: 'Alles: zichtbare huishoudartikelen' }).check()
  await page.getByRole('button', { name: 'Bonregels beoordelen (2)' }).click()
  const sources = page.getByTestId('catalog-conflict-sources-table')
  const identical = sources.getByRole('checkbox', { name: 'Selecteer bonartikelnummer 0012345' })
  await expect(identical).toHaveCount(2)
  await identical.first().check()
  await identical.last().check()
  await page.getByRole('button', { name: 'Barcode bepalen (2)' }).click()
  await page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })
    .getByLabel('Juiste Artikel-/barcode').fill('8712345678906')
  await page.getByRole('dialog', { name: 'Artikelbarcode bij bonartikel bevestigen' })
    .getByRole('button', { name: 'Barcode bevestigen' }).click()
  await expect.poll(() => getCaptured()?.external_article_code).toBe('0012345')
  await expect(page.getByText('Dit lost eventuele dubbele huishoudartikelen niet op')).toBeVisible()
})
