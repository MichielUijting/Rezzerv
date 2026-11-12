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
    sources: [{ receipt_line_id: 'line-3', retailer_code: 'lidl',
      receipt_text: 'melk halfvol', external_article_code: '0012345',
      receipt_count: 3, identity_status: 'matched', candidate_product_id: 'product-1' }],
  }],
}

async function mockCatalog(page, { canReview = true, failSave = false, ordinaryAdmin = false } = {}) {
  let captured = null
  await page.route('**/api/session', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({
      user_id: 'test-owner', active_household_id: '1', context_type: 'regular',
      role: canReview ? 'owner' : 'viewer', display_role: canReview ? 'admin' : 'viewer',
      permissions: { 'platform.external_products.link_existing': canReview,
        'admin.access': canReview },
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
  await page.getByTestId('catalog-conflicts-table').getByRole('button', { name: 'Bonregels beoordelen' }).first().click()
  const evidence = page.getByTestId('catalog-conflict-sources-table')
  await expect(evidence.getByText('0012345')).toBeVisible()
  await expect(evidence.getByText('0087654')).toBeVisible()
  await evidence.getByRole('button', { name: 'Barcode bepalen' }).nth(1).click()
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
  await page.getByTestId('catalog-conflicts-table').getByRole('button', { name: 'Bonregels beoordelen' }).first().click()
  await page.getByTestId('catalog-conflict-sources-table').getByRole('button', { name: 'Barcode bepalen' }).first().click()
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
  await page.route('**/api/platform/frontteam-management', route => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ frontteam_memberships: [] }),
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
    const guidance = page.getByTestId('catalog-frontteam-review-guidance')
    await expect(guidance).toContainText('regulier account')
    await guidance.getByRole('button', { name: 'Naar Frontteambeheer' }).click()
    await expect(page).toHaveURL(/\/superuser\?tab=frontteam$/)
    await expect(page.getByTestId('superuser-control-tab-frontteam')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('settings-frontteam-page')).toBeVisible()
    await expect(page.getByTestId('frontteam-catalog-review-help')).toContainText('eigen huishouden')
    expect(getReviewRequests()).toBe(1)
  })
}

for (const [name, width, height] of [
  ['desktop', 1280, 800],
  ['mobiel', 390, 844],
]) {
  test(`Gewone beheerder met technische koppelingpermissie ziet geen historische beoordeling op ${name}`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await mockCatalog(page, { ordinaryAdmin: true })
    await page.goto('/catalogus')
    await expect(page.getByRole('button', { name: 'Historische conflicten beoordelen' })).toHaveCount(0)
  })
}
