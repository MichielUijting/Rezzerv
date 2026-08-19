import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

function recognitionReceiptItems(confirmed) {
  const recognitionItem = {
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
    external_match_status: confirmed ? 'external_resolved' : '',
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
        external_match_status: confirmed ? 'external_resolved' : '',
        is_user_confirmed: 0,
        is_external_database_override: 0,
        global_product_id: null,
        is_linked_to_catalog: false,
        central_link_active: false,
      },
    ],
  }

  const fillerItems = Array.from({ length: 11 }, (_, index) => ({
    receipt_item_id: `purchase-import-line:recognition-filler-${index + 1}`,
    receipt_item_type: 'purchase_import_line',
    receipt_item_source_id: `recognition-filler-${index + 1}`,
    purchase_import_line_id: `recognition-filler-${index + 1}`,
    context_key: `purchase-import-line:recognition-filler-${index + 1}`,
    receipt_line_text: `Z testregel ${String(index + 1).padStart(2, '0')}`,
    retailer_code: 'lidl',
    quantity_label: '1 stuk',
    price: 0.99 + index,
    status: 'candidate',
    candidate_status: 'candidate',
    is_receipt_item_placeholder: true,
    candidates: [],
  }))

  return [recognitionItem, ...fillerItems]
}

test.describe('Externe herkenning bevestigen geïntegreerde regressie', () => {
  test('behoudt volwassen overzichtsfuncties en bevestigt herkenning in hetzelfde detail', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    let confirmed = false
    let confirmationPayload = null

    await page.route('**/api/external-databases/summary', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ module: 'Externe databases', supported_retailers: 1 }) })
    })
    await page.route('**/api/external-databases/retailers', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ retailers: [{ retailer_code: 'lidl', retailer_name: 'Lidl', status: 'active' }] }) })
    })
    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: recognitionReceiptItems(confirmed) }) })
    })
    await page.route('**/api/inventory/groups', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ group_options: [] }) })
    })
    await page.route('**/api/external-products/off/search', async (route) => {
      const payload = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, status: 'no_results', provider: 'search_a_licious', query: payload?.query || 'Veldsla herkenning regressietest', results: [] }),
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

    // Eén hoofdlijst: de volwassen bonartikelentabel. De regressieve tweede lijst mag niet terugkomen.
    await expect(page.getByTestId('external-recognition-items-table')).toHaveCount(0)
    const table = page.getByTestId('external-receipt-items-table')
    await expect(table).toBeVisible()

    // Het bestaande generieke sticky-tabelpatroon borgt kop + filterrij.
    await expect(table).toHaveClass(/rz-data-table--sticky-header/)
    await expect(table).toHaveClass(/rz-data-table--sticky-filters/)
    const headerCell = table.locator('thead tr.rz-table-header th').first()
    const filterCell = table.locator('thead tr.rz-table-filters th').first()
    await expect(headerCell).toHaveCSS('position', 'sticky')
    await expect(filterCell).toHaveCSS('position', 'sticky')

    // Meer dan tien regels moet de bestaande paginering activeren.
    await expect(page.getByText('Pagina 1 van 2')).toBeVisible()
    await page.getByRole('button', { name: 'Volgende', exact: true }).click()
    await expect(page.getByText('Pagina 2 van 2')).toBeVisible()
    await page.getByRole('button', { name: 'Eerste', exact: true }).click()
    await expect(page.getByText('Pagina 1 van 2')).toBeVisible()

    // Bestaande filters blijven werken.
    const receiptFilter = table.getByRole('textbox', { name: 'Filter op Bonartikel' })
    await receiptFilter.fill('Veldsla')
    await expect(table.locator('tbody tr', { hasText: 'Veldsla herkenning regressietest' })).toBeVisible()
    await expect(table.locator('tbody tr', { hasText: 'Z testregel 01' })).toHaveCount(0)
    await receiptFilter.fill('')

    // Het bestaande detail blijft de plek voor alle vervolgacties.
    const receiptRow = table.locator('tbody tr', { hasText: 'Veldsla herkenning regressietest' })
    await receiptRow.dblclick()
    await expect(page.getByLabel('OFF zoektekst')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Zelf zoeken', exact: true })).toBeVisible()

    const recognitionDetail = page.getByTestId('external-recognition-detail')
    await expect(recognitionDetail).toBeVisible()
    await expect(recognitionDetail).toContainText('Herkenning bevestigen')
    const candidateTable = page.getByTestId('external-recognition-candidates-table')
    await expect(candidateTable).toContainText('Lidl Veldsla')
    await expect(candidateTable).toContainText('lidl_catalog_enrichment')
    await expect(candidateTable).toContainText('lidl:groente.veldsla')
    await candidateTable.locator('input[type="radio"]').check()

    await page.getByRole('button', { name: 'Bevestig herkenning', exact: true }).click()

    await expect.poll(() => confirmationPayload).not.toBeNull()
    expect(confirmationPayload).toEqual({ candidate_id: 'recognition-candidate-1', force_overwrite: false })
    await expect(page.getByTestId('external-recognition-feedback')).toContainText('Herkenning bevestigd')
    await expect(candidateTable).toContainText('Herkenning bevestigd')
    await expect(recognitionDetail).toContainText('lidl_catalog_enrichment')
    await expect(recognitionDetail).toContainText('lidl:groente.veldsla')

    // Bevestigen blijft los van Catalogus/Producttype.
    expect(confirmationPayload).not.toHaveProperty('global_product_id')
    await expectNoConsoleErrors(consoleErrors)
  })
})
