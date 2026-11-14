import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })
const barcode = '8712345678906'
const code = '0082346'

async function startArticlebeheer(page, { found = true } = {}) {
  const requests = []
  let linked = false
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'article-identity-test', active_household_id: '0', role: 'owner',
      context_type: 'system', is_platform_superuser: true,
      permissions: { 'platform.external_products.link_existing': true },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: [{
        id: 'receipt-table-line:l1', receipt_line_text: 'Lidl halfvolle melk',
        retailer_code: 'lidl', receipt_article_number: code,
        article_code: linked ? barcode : '', link_status: linked ? 'linked' : 'unlinked',
        quantity_label: '1 liter', manual_barcode: '',
      }],
      counts: { unlinked: linked ? 0 : 1, classification_pending: 0, linked: linked ? 1 : 0 },
    } })
    if (path === '/api/external-databases/products/search-preview') {
      return route.fulfill({ json: { provider: 'none', results: [] } })
    }
    if (path === `/api/barcodes/${barcode}` && route.request().method() === 'GET') {
      return route.fulfill({ json: found
        ? { valid: true, match_status: 'incomplete',
            product: { global_product_id: 'p1', name: 'Halfvolle melk', status: 'active' } }
        : { valid: true, match_status: 'not_found', product: null } })
    }
    if (path === '/api/barcodes/confirm-retailer-code' && route.request().method() === 'POST') {
      const data = route.request().postDataJSON()
      requests.push(data)
      linked = true
      return route.fulfill({ json: { status: 'confirmed', global_product_id: 'p1',
        historical_repair: { status: 'linked', updated: 1 } } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'Lidl halfvolle melk' }).dblclick()
  await expect(page.getByTestId('ed2-manual-barcode-entry')).toBeVisible()
  return requests
}

test('Artikelbeheer: check product, require explicit overlay OK, then one central write', async ({ page }) => {
  const writes = await startArticlebeheer(page)
  const panel = page.getByTestId('ed2-manual-barcode-entry')
  await panel.getByTestId('ed2-manual-barcode-input').fill(barcode)
  await panel.getByTestId('ed2-catalog-identity-check').click()
  const dialog = page.getByTestId('ed2-catalog-identity-confirm-overlay')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('Halfvolle melk')
  await expect(dialog).toContainText(code)
  expect(writes).toHaveLength(0)
  await dialog.getByRole('button', { name: 'Annuleren' }).click()
  expect(writes).toHaveLength(0)

  await panel.getByTestId('ed2-catalog-identity-check').click()
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Koppelen', exact: true }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]).toEqual({
    receipt_item_id: 'receipt-table-line:l1',
    retailer_code: 'lidl', external_article_code: code, gtin: barcode,
  })
  await expect(page.getByTestId('external-databases-2-table')).toContainText('Lidl halfvolle melk')
  await expect(page.getByText(/bestaand huishoudartikel automatisch bijgewerkt/i)).toBeVisible()
})

test('Artikelbeheer: unknown Catalogus GTIN never confirms by name or code alone', async ({ page }) => {
  const writes = await startArticlebeheer(page, { found: false })
  const panel = page.getByTestId('ed2-manual-barcode-entry')
  await panel.getByTestId('ed2-manual-barcode-input').fill(barcode)
  await panel.getByTestId('ed2-catalog-identity-check').click()
  await expect(page.getByTestId('ed2-catalog-identity-not-found-overlay')).toBeVisible()
  expect(writes).toHaveLength(0)
  await expect(panel.getByTestId('ed2-manual-barcode-save')).toBeEnabled()
  await expect(page.getByTestId('ed2-catalog-identity-confirm-overlay')).toHaveCount(0)
})


test('Lidl: individual correction previews, can cancel and writes only after confirmation', async ({ page }) => {
  const oldCode = '2008234600001'
  const newCode = '2012345678903'
  let savedCode = oldCode
  const confirmations = []
  let previews = 0
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'frontteam-editor', active_household_id: '0', context_type: 'system',
      role: 'member', is_platform_superuser: false, is_frontteam: true,
      permissions: { 'platform.external_products.link_existing': true },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: [{
        id: 'receipt-table-line:lidl-correction', receipt_line_text: 'Lidl courgette groen',
        retailer_code: 'lidl', receipt_article_number: '123',
        article_code: '', link_status: 'unlinked',
        quantity_label: '1 stuk', manual_barcode: savedCode,
      }],
      counts: { unlinked: 1, linked: 0, classification_pending: 0 },
    } })
    if (path === '/api/external-databases/products/search-preview') {
      return route.fulfill({ json: { provider: 'none', results: [] } })
    }
    if (path === '/api/catalog/ed2/manual-barcodes/lidl/preview-correction') {
      previews++
      expect(route.request().postDataJSON()).toEqual({
        receipt_item_id: 'receipt-table-line:lidl-correction', new_gtin: newCode,
      })
      return route.fulfill({ json: {
        can_confirm: true, receipt_item_id: 'receipt-table-line:lidl-correction',
        old_gtin: oldCode, new_gtin: newCode, new_scope: 'restricted',
        new_product_will_be_created: true, preview_fingerprint: 'a'.repeat(64),
        legacy_link_count: 0, household_article_count: 0, blocked_reasons: [],
      } })
    }
    if (path === '/api/catalog/ed2/manual-barcodes/lidl/confirm-correction') {
      confirmations.push(route.request().postDataJSON())
      savedCode = newCode
      return route.fulfill({ json: {
        corrected: true, old_gtin: oldCode, gtin: newCode,
        barcode_scope: 'restricted', global_product_id: 'new-lidl-product',
        catalog_product_created: true, stock_changes: 0,
      } })
    }
    return route.fulfill({ json: {} })
  })

  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'Lidl courgette groen' }).dblclick()
  const correction = page.getByTestId('ed2-lidl-barcode-correction')
  await expect(correction).toBeVisible()
  await expect(correction).toContainText(oldCode)
  await expect(page.getByTestId('ed2-manual-barcode-save')).toHaveCount(0)
  await correction.getByTestId('ed2-lidl-correction-input').fill(newCode)
  await correction.getByTestId('ed2-lidl-correction-preview').click()
  const confirm = page.getByTestId('ed2-lidl-correction-confirm-overlay')
  await expect(confirm).toBeVisible()
  await expect(confirm).toContainText(oldCode)
  await expect(confirm).toContainText(newCode)
  expect(confirmations).toHaveLength(0)
  await confirm.getByRole('button', { name: 'Annuleren' }).click()
  expect(confirmations).toHaveLength(0)

  await correction.getByTestId('ed2-lidl-correction-preview').click()
  await expect(confirm).toBeVisible()
  await confirm.getByRole('button', { name: 'Correctie bevestigen' }).click()
  await expect.poll(() => confirmations.length).toBe(1)
  expect(confirmations[0]).toEqual({
    receipt_item_id: 'receipt-table-line:lidl-correction',
    new_gtin: newCode, expected_old_gtin: oldCode,
    preview_fingerprint: 'a'.repeat(64),
  })
  expect(previews).toBe(2)
  await expect(page.getByText(/Lidl-barcode gecorrigeerd/)).toBeVisible()
})

test('Lidl: historical conflict preview never offers the confirmation action', async ({ page }) => {
  let writes = 0
  const oldCode = '2008234600001'
  await page.route('**/api/**', (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'frontteam-editor', active_household_id: '0', context_type: 'system',
      role: 'member', is_platform_superuser: false, is_frontteam: true,
      permissions: { 'platform.external_products.link_existing': true },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
      items: [{
        id: 'receipt-table-line:blocked-lidl', receipt_line_text: 'Lidl groene courgette',
        retailer_code: 'lidl', receipt_article_number: '456',
        article_code: '', link_status: 'linked', manual_barcode: oldCode,
      }],
      counts: { unlinked: 0, linked: 1, classification_pending: 0 },
    } })
    if (path === '/api/external-databases/products/search-preview') {
      return route.fulfill({ json: { provider: 'none', results: [] } })
    }
    if (path === '/api/catalog/ed2/manual-barcodes/lidl/preview-correction') {
      return route.fulfill({ json: {
        can_confirm: false, blocked_reasons: [
          'Er bestaat nog een bevestigde andere Cataloguskoppeling.',
        ],
      } })
    }
    if (path === '/api/catalog/ed2/manual-barcodes/lidl/confirm-correction') {
      writes++
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/externe-databases-2')
  await page.getByTestId('classification-work-monitor')
    .getByRole('button', { name: 'Identificeren' }).click()
  await page.getByTestId('external-databases-2-table')
    .locator('tbody tr', { hasText: 'Lidl groene courgette' }).dblclick()
  const correction = page.getByTestId('ed2-lidl-barcode-correction')
  await expect(correction).toBeVisible()
  await correction.getByTestId('ed2-lidl-correction-input').fill('2012345678903')
  await correction.getByTestId('ed2-lidl-correction-preview').click()
  const blocked = page.getByTestId('ed2-lidl-correction-blocked-overlay')
  await expect(blocked).toBeVisible()
  await expect(blocked).toContainText('bevestigde andere Cataloguskoppeling')
  expect(writes).toBe(0)
})
