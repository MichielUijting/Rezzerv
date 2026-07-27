import { test, expect } from '@playwright/test'

const HOUSEHOLD_ID = '1'
const ARTICLE_ID = '58eff2cd-fdde-40e1-92e0-5ab79fd04b7b'

test('handmatige Producttypeselectie zoekt, selecteert en bevestigt expliciet', async ({ page }) => {
  let confirmationPayload = null

  await page.addInitScript(() => {
    localStorage.setItem('rezzerv_token', 'frontend-regression-token')
    localStorage.setItem('rezzerv_active_household_id', '1')
  })

  await page.route('**/api/external-databases/summary', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ household_id: HOUSEHOLD_ID }) }))
  await page.route('**/api/external-databases/retailers', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ retailers: [] }) }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/product-type-resolution-proposals`, async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ items: [{ household_article_id: ARTICLE_ID, inventory_name: 'Pizza' }] }),
  }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/product-type-catalog-search**`, async (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      items: [{
        gpc_brick_code: '10000248',
        display_name: "Taarten/Gebakjes/Pizza's/Quiches - Hartig (Diepvries)",
        gpc_class_name: 'Hartige Bakkerijproducten',
        gpc_family_name: 'Brood/Bakkerij Producten',
      }],
    }),
  }))
  await page.route(`**/api/households/${HOUSEHOLD_ID}/product-type-selection/confirm`, async (route) => {
    confirmationPayload = route.request().postDataJSON()
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        selected_product_type: { display_name: "Taarten/Gebakjes/Pizza's/Quiches - Hartig (Diepvries)" },
      }),
    })
  })
  await page.route('**/api/external-databases/linked-receipt-articles**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [], total: 0, page_count: 1 }) }))
  await page.route('**/api/**', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))

  await page.goto('/externe-databases')

  const panel = page.getByTestId('product-type-manual-selection-panel')
  await expect(panel).toBeVisible()
  await expect(panel.getByText('Pizza')).toBeVisible()

  await panel.getByRole('button', { name: 'Zoeken' }).click()
  await expect(page.getByTestId('product-type-catalog-search-results')).toBeVisible()
  await panel.getByRole('button', { name: 'Selecteren' }).click()
  await expect(panel.getByRole('dialog', { name: 'Producttype bevestigen' })).toBeVisible()
  await panel.getByRole('button', { name: 'Bevestigen en opslaan' }).click()

  expect(confirmationPayload).toEqual({
    household_article_id: ARTICLE_ID,
    gpc_brick_code: '10000248',
    confirmed: true,
  })
})
