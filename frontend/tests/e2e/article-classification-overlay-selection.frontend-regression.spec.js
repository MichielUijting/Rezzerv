import { test, expect } from '@playwright/test'

test.use({ storageState: { cookies: [], origins: [] } })

test('Artikelbeheer: selecteer officiële GS1/CBS-resultaatregel en sla veilig op', async ({ page }) => {
  const writes = []
  let gpcBrick = '10000001'
  let cbsCode = ''
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()
    if (path === '/api/session') return route.fulfill({ json: {
      user_id: 'test-superuser', context_type: 'system', active_household_id: '0',
      is_platform_superuser: true, role: 'owner', permissions: { 'gpc.update': true },
    } })
    if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
    if (path === '/api/onboarding') return route.fulfill({ json: { onboarding_status: 'completed' } })
    if (path === '/api/features') return route.fulfill({ json: { features: {} } })
    if (path === '/api/action-buttons') return route.fulfill({ json: { items: [] } })
    if (path === '/api/cbs-classifications/products') return route.fulfill({ json: {
      total: 1, items: [{ id: 'p1', name: 'Testmelk', brand: 'Voorbeeld',
        gtin: '8712345678901', classified: Boolean(cbsCode), cbs_code: cbsCode,
        category_name: cbsCode ? 'Melk' : '', version: cbsCode ? 1 : 0 }],
    } })
    if (path === '/api/catalog/p1/gpc-brick' && method === 'GET') return route.fulfill({ json: {
      assignment: { brick_code: gpcBrick, brick_description: 'Melk' }, suggestions: [],
    } })
    if (path === '/api/catalog/gpc/bricks' && method === 'GET') return route.fulfill({ json: {
      items: [{ brick_code: '10000002', brick_description: 'Andere melk',
        segment_description: 'Voeding', family_description: 'Zuivel' }],
    } })
    if (path === '/api/catalog/p1/gpc-brick' && method === 'PUT') {
      const body = route.request().postDataJSON()
      writes.push({ path, body })
      gpcBrick = body.brick_code
      return route.fulfill({ json: { assignment: {
        brick_code: gpcBrick, brick_description: 'Andere melk',
      } } })
    }
    if (path === '/api/cbs-classifications/categories') return route.fulfill({ json: {
      items: [{ cbs_code: '011420', name_nl: 'Melk',
        reference_version: 'CBS-ECOICOPv2-2026', lowest: true, path: 'Voeding › Melk' }],
    } })
    if (path === '/api/cbs-classifications/bulk-confirm' && method === 'POST') {
      const body = route.request().postDataJSON()
      writes.push({ path, body })
      cbsCode = body.selections[0].cbs_code
      return route.fulfill({ json: { confirmed: 1, unchanged: 0 } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/externe-databases-2')
  await page.getByRole('button', { name: 'Classificeren', exact: true }).click()
  await page.getByTestId('combined-classification-articles').getByRole('row', { name: /Testmelk/ }).click()
  await expect(page.getByTestId('classification-gs1-panel')).toContainText('10000001')
  await expect(page.getByTestId('cbs-automatic-suggestions')).toContainText('011420')
  expect(writes).toHaveLength(0)

  await page.getByTestId('classification-gs1-panel').getByRole('button', { name: 'Andere Brick kiezen' }).click()
  const gpcDialog = page.getByRole('dialog', { name: 'GS1 GPC Brick kiezen' })
  await gpcDialog.getByPlaceholder('Zoek categorie of code').fill('melk')
  await gpcDialog.getByRole('button', { name: /10000002.*Andere melk/ }).click()
  await expect.poll(() => writes.length).toBe(1)
  expect(writes[0]).toEqual({ path: '/api/catalog/p1/gpc-brick', body: { brick_code: '10000002' } })
  await expect(page.getByTestId('classification-gs1-panel')).toContainText('10000002')

  await page.getByTestId('cbs-automatic-suggestions').getByRole('button', { name: /011420.*Melk/ }).click()
  await expect.poll(() => writes.length).toBe(2)
  expect(writes[1].path).toBe('/api/cbs-classifications/bulk-confirm')
  expect(writes[1].body.selections).toEqual([{
    global_product_id: 'p1', expected_product_name: 'Testmelk',
    cbs_code: '011420', reference_version: 'CBS-ECOICOPv2-2026', expected_version: 0,
  }])
  await expect(page.getByTestId('cbs-single-product')).toContainText('011420')
})
