import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  test(`ED2 vraagt expliciete bevestiging voor GS1-classificatie op ${width}px`, async ({ page }) => {
    const id = 'receipt-table-line:achterham'
    const productId = 'catalog-achterham'
    const linkId = 'off-pending-achterham'
    let linked = false
    const posts = []

    await page.setViewportSize({ width, height: 900 })
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'test-superuser', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true,
        permissions: { 'platform.system_household.access': true },
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
      if (path === '/api/features') return route.fulfill({ json: { features: {} } })
      if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: [{ id, receipt_line_text: 'Achterham BL', retailer_code: 'lidl',
          receipt_article_number: '6604471', article_code: '8718452504435',
          link_status: linked ? 'linked' : 'classification_pending',
          off_link_id: linkId, pending_global_product_id: linked ? '' : productId }],
        total: 1, counts: { unlinked: 0, classification_pending: linked ? 0 : 1, linked: linked ? 1 : 0 },
      } })
      if (path === `/api/catalog/${productId}/gpc-brick`) return route.fulfill({ json: {
        assignment: null,
        suggestions: [{ brick_code: '10000001', brick_description: 'Vleeswaren',
          family_description: 'Vleesproducten' }],
      } })
      if (path === '/api/catalog/gpc/bricks') return route.fulfill({ json: {
        items: [{ brick_code: '10000001', brick_description: 'Vleeswaren',
          family_description: 'Vleesproducten' }],
      } })
      if (path === '/api/external-databases/off/classify-pending') {
        posts.push(request.postDataJSON())
        linked = true
        return route.fulfill({ json: {
          ok: true, linked: true, receipt_item_id: id,
          global_product_id: productId, gpc_brick_code: '10000001',
        } })
      }
      return route.fulfill({ json: {} })
    })

    await page.goto('/externe-databases-2')
    await expect(page.getByRole('button', { name: 'Classificatie ontbreekt: 1' })).toBeVisible()
    const table = page.getByTestId('external-databases-2-table')
    const source = table.locator('tbody tr').filter({ hasText: 'Achterham BL' })
    if (width <= 720) await source.click()
    else await source.dblclick()

    const panel = page.getByTestId('ed2-gpc-panel')
    await expect(panel).toBeVisible()
    await expect(panel.getByText('Achterham BL')).toHaveCSS('font-weight', '700')
    const search = panel.getByRole('textbox', { name: 'Zoeken op GS1-code of productnaam' })
    await search.fill('1000')
    await panel.getByRole('button', { name: 'Zoeken' }).click()
    const candidate = page.getByTestId('ed2-gpc-candidates').locator('tbody tr').first()
    await expect(candidate).toContainText('Vleeswaren')
    await candidate.click()
    await panel.getByRole('button', { name: 'Classificatie opslaan' }).click()
    await expect(page.getByRole('alertdialog')).toContainText('10000001')
    await page.getByRole('button', { name: 'Annuleren' }).click()
    expect(posts).toHaveLength(0)
    await panel.getByRole('button', { name: 'Classificatie opslaan' }).click()
    await page.getByRole('button', { name: 'OK', exact: true }).click()
    await expect(page.getByTestId('external-off-link-outcome')).toContainText('het bonartikel is gekoppeld')
    await expect(page.getByRole('button', { name: 'Gekoppeld: 1' })).toBeVisible()
    await expect(page.getByTestId('ed2-gpc-panel')).toHaveCount(0)
    expect(posts).toEqual([{ receipt_item_id: id, link_id: linkId, brick_code: '10000001' }])
  })
}
