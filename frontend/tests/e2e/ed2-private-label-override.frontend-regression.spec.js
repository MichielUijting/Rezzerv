import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const mobile of [false, true]) {
  test(`AH CRACKERS → Lu: Melding met Annuleren en Toch koppelen (${mobile ? 'mobiel' : 'desktop'})`, async ({ page }) => {
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1350, height: 900 })
    const item = { id: 'receipt-table-line:ah-crackers', receipt_line_text: 'AH CRACKERS',
      retailer_code: 'ah', retailer: 'Albert Heijn', receipt_article_number: '1234',
      article_code: '', link_status: 'unlinked' }
    const candidate = { gtin: '7622210475152', product_name: 'Mini crackers nature',
      brand: 'Lu', quantity: '250 g', score: .78, identity_compatible: false,
      identity_conflict_reason: 'private_label_brand_conflict',
      identity_conflict_message: 'AH CRACKERS lijkt een huismerkartikel; merk Lu wijkt af.',
      selection_proof: 'signed-ah-crackers-off-proof' }
    const writes = []
    await page.route('**/api/**', (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'po-override', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true,
        permissions: { 'platform.system_household.access': true },
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: [item], counts: { unlinked: 1, classification_pending: 0, linked: 0 },
      } })
      if (path === '/api/external-databases/products/search-preview') return route.fulfill({ json: { results: [] } })
      if (path === '/api/external-products/off/search') return route.fulfill({ json: {
        provider: 'openfoodfacts', results: [candidate],
      } })
      if (path === '/api/external-databases/off/link-selected') {
        writes.push(route.request().postDataJSON())
        return route.fulfill({ json: { cataloged: true, classification_pending: true } })
      }
      return route.fulfill({ json: {} })
    })
    await page.goto('/externe-databases-2')
    const article = page.getByTestId('external-databases-2-table')
      .locator('tbody tr', { hasText: 'AH CRACKERS' })
    if (mobile) await article.click()
    else await article.dblclick()
    await page.getByRole('button', { name: 'Zelf zoeken in OFF' }).click()
    await page.getByRole('textbox', { name: 'Omschrijving of barcode in OFF' }).fill('crackers')
    await page.getByRole('button', { name: 'Zoeken', exact: true }).click()
    const result = page.getByTestId('external-off-free-search-results').locator('tbody tr', { hasText: 'Lu' })
    if (mobile) await result.click()
    else await result.dblclick()
    const warning = page.getByTestId('ed2-private-label-override-warning')
    await expect(warning).toBeVisible()
    await expect(warning).toContainText('AH CRACKERS')
    await expect(warning).toContainText('Lu')
    await expect(warning.getByRole('button', { name: 'Annuleren' })).toBeVisible()
    await expect(warning.getByRole('button', { name: 'Toch koppelen' })).toBeVisible()
    expect(writes).toHaveLength(0)
    await warning.getByRole('button', { name: 'Annuleren' }).click()
    await expect(warning).toHaveCount(0)
    expect(writes).toHaveLength(0)

    if (mobile) await result.click()
    else await result.dblclick()
    await page.getByTestId('ed2-private-label-override-warning')
      .getByRole('button', { name: 'Toch koppelen' }).click()
    await expect(page).toHaveURL(/\/externe-databases-2$/)
    expect(writes).toEqual([{
      receipt_item_id: item.id, gtin: candidate.gtin,
      selection_proof: candidate.selection_proof,
      override_private_label_conflict: true,
    }])
  })
}
