import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

function recognitionReceiptItems(confirmed) {
  return [
    {
      receipt_item_id: 'purchase-import-line:recognition-regression-line',
      receipt_item_type: 'purchase_import_line',
      receipt_item_source_id: 'recognition-regression-line',
      purchase_import_line_id: 'recognition-regression-line',
      context_key: 'purchase-import-line:recognition-regression-line',
      receipt_line_text: 'Veldsla herkenning regressietest',
      retailer_code: 'lidl',
      quantity_label: '1 stuk',
      price: 1.49,
      status: confirmed ? 'external_resolved' : 'candidate',
      candidate_status: confirmed ? 'external_resolved' : 'candidate',
      is_receipt_item_placeholder: true,
      candidates: [
        {
          id: 'recognition-candidate-1',
          context_key: 'purchase-import-line:recognition-regression-line',
          purchase_import_line_id: 'recognition-regression-line',
          receipt_line_text: 'Veldsla herkenning regressietest',
          retailer_code: 'lidl',
          candidate_name: 'Lidl Veldsla',
          candidate_brand: 'Lidl',
          candidate_source_name: 'lidl_catalog_enrichment',
          candidate_source_product_code: 'lidl:groente.veldsla',
          source_name: 'lidl_catalog_enrichment',
          source_product_code: 'lidl:groente.veldsla',
          retailer_article_number: 'lidl:groente.veldsla',
          score: 0.95,
          status: confirmed ? 'external_resolved' : 'probable_candidate',
          candidate_status: confirmed ? 'external_resolved' : 'probable_candidate',
          is_user_confirmed: 0,
          is_external_database_override: 0,
          global_product_id: null,
          is_linked_to_catalog: false,
        },
      ],
    },
  ]
}

test.describe('Externe herkenning bevestigen frontend-regressie', () => {
  test('bevestigt bronherkenning zonder de Catalogus-flow te gebruiken', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let confirmed = false
    let confirmationPayload = null

    await page.route('**/api/external-databases/summary', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ module: 'Externe databases', supported_retailers: 1 }),
      })
    })
    await page.route('**/api/external-databases/retailers', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ retailers: [{ retailer_code: 'lidl', retailer_name: 'Lidl', status: 'active' }] }),
      })
    })
    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: recognitionReceiptItems(confirmed) }),
      })
    })
    await page.route('**/api/external-databases/candidates/confirm-external', async (route) => {
      confirmationPayload = route.request().postDataJSON()
      confirmed = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          confirmed: true,
          requires_overwrite: false,
          candidate_id: 'recognition-candidate-1',
          external_product_code: 'lidl:groente.veldsla',
          external_source_name: 'lidl_catalog_enrichment',
          creates_global_product: false,
          creates_product_identity: false,
          creates_household_article: false,
          creates_inventory_event: false,
        }),
      })
    })

    await page.goto('/externe-databases')

    const panel = page.getByTestId('external-recognition-panel')
    await expect(panel).toBeVisible()
    await expect(panel).toContainText('Herkenning bevestigen')
    await expect(panel).toContainText('geen cataloguskoppeling')

    const table = page.getByTestId('external-recognition-items-table')
    const row = table.locator('tbody tr', { hasText: 'Veldsla herkenning regressietest' })
    await expect(row).toBeVisible()
    await expect(row).toContainText('lidl_catalog_enrichment')
    await expect(row).toContainText('lidl:groente.veldsla')
    await expect(row).toContainText('Herkenning beschikbaar')

    await row.dblclick()

    const candidateTable = page.getByTestId('external-recognition-candidates-table')
    await expect(candidateTable).toBeVisible()
    await expect(candidateTable).toContainText('Lidl Veldsla')
    await expect(candidateTable).toContainText('lidl_catalog_enrichment')
    await expect(candidateTable).toContainText('lidl:groente.veldsla')
    await expect(candidateTable.locator('input[type="radio"]')).toBeChecked()

    await page.getByRole('button', { name: 'Bevestig herkenning', exact: true }).click()

    await expect.poll(() => confirmationPayload).not.toBeNull()
    expect(confirmationPayload).toEqual({
      candidate_id: 'recognition-candidate-1',
      force_overwrite: false,
    })

    await expect(page.getByTestId('external-recognition-feedback')).toContainText('Herkenning bevestigd')
    await expect(row).toContainText('Herkenning bevestigd')
    await expect(candidateTable).toContainText('Herkenning bevestigd')
    await expect(page.getByRole('button', { name: 'Koppel artikel en Producttype', exact: true })).toHaveCount(0)
    await expectNoConsoleErrors(consoleErrors)
  })
})
