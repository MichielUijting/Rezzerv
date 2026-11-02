import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

for (const width of [390, 1280]) {
  for (const role of ['superuser', 'frontteam']) {
    test(`CBS: expliciet classificeren zonder barcode als ${role} op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const writes = []
      let saved = false
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
        if (path === '/api/session') return route.fulfill({ json: {
          user_id: 'cbs-ci-user', active_household_id: role === 'superuser' ? '0' : 'household-test',
          context_type: role === 'superuser' ? 'system' : 'regular', role: 'admin',
          is_platform_superuser: role === 'superuser', is_frontteam: role === 'frontteam',
          permissions: { 'platform.external_products.view': true, 'platform.external_products.link_existing': true },
        } })
        if (path === '/api/cbs-classifications/products') {
          return route.fulfill({ json: { total: 1, items: [{
            id: 'central-milk', name: 'Halfvolle melk', brand: 'Jumbo', gtin: '',
            cbs_code: saved ? '011420' : '', category_name: saved ? 'Halfvolle en magere melk (ND)' : '',
            reference_version: saved ? 'CBS-ECOICOPv2-2026' : '', version: saved ? 1 : 0,
            classified: saved,
          }] } })
        }
        if (path === '/api/cbs-classifications/categories') {
          return route.fulfill({ json: { total: 1, items: [{
            cbs_code: '011420', name_nl: 'Halfvolle en magere melk (ND)',
            parent_code: '011400', level: 4, lowest: true,
            reference_version: 'CBS-ECOICOPv2-2026',
            path: 'Voedingsmiddelen en alcoholvrije dranken › Voedingsmiddelen › Melk › Halfvolle en magere melk (ND)',
          }] } })
        }
        if (path === '/api/cbs-classifications/bulk-confirm') {
          writes.push(route.request().postDataJSON())
          saved = true
          return route.fulfill({ json: { confirmed: 1, unchanged: 0 } })
        }
        if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
        if (path === '/api/features') return route.fulfill({ json: { features: {} } })
        if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
        return route.fulfill({ json: {} })
      })
      await page.goto('/catalogus/artikelclassificaties-toekennen')
      await expect(page.getByRole('heading', { name: 'Artikelclassificaties toekennen' }).first()).toBeVisible()
      await expect(page.getByTestId('cbs-classification-table')).toContainText('Niet geclassificeerd')
      await page.getByLabel('Selecteer Halfvolle melk').check()
      await page.getByPlaceholder('Bijvoorbeeld melk of 011420').fill('011420')
      await page.getByRole('button', { name: 'Voorstel ophalen' }).click()
      await expect(page.getByTestId('cbs-category-candidates')).toContainText('011420')
      expect(writes).toHaveLength(0)
      await page.getByTestId('cbs-category-candidates').getByRole('button', { name: 'Kiezen' }).click()
      await page.getByRole('button', { name: 'Voorstel bevestigen' }).click()
      expect(writes).toHaveLength(0)
      await page.getByRole('button', { name: 'Bevestigen', exact: true }).click()
      await expect.poll(() => writes.length).toBe(1)
      expect(writes[0].selections).toEqual([{
        global_product_id: 'central-milk',
        expected_product_name: 'Halfvolle melk',
        cbs_code: '011420', reference_version: 'CBS-ECOICOPv2-2026',
        expected_version: 0,
      }])
      await expect(page.getByTestId('cbs-classification-table')).toContainText('011420')
    })
  }
}
