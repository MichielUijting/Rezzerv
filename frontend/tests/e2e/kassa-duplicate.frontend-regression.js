import { test, expect } from '@playwright/test'

const scenarios = ['active', 'processed', 'unpacking', 'rejected', 'archived'].flatMap((state) =>
  (state === 'archived' ? ['upload'] : ['upload', 'share']).map((source) => ({ state, source })))

for (const { state, source } of scenarios) {
  test(`duplicate ${state} ${source}: current backend lifecycle controls feedback and opening`, async ({ page }) => {
    const writes = []
    const receipt = {
      id: 'duplicate-receipt', receipt_table_id: 'duplicate-receipt',
      store_name: 'Testwinkel', purchase_at: '2026-09-01', total_amount: 2,
      approved_at: ['processed', 'unpacking'].includes(state) ? '2026-09-01T12:00:00' : null,
      import_status: state === 'processed' ? 'processed' : null,
      // Even an approved parser result does not mean inventory was processed.
      parse_status: state === 'rejected' ? 'rejected' : 'approved',
      po_norm_status_label: 'Controle nodig', lines: [],
    }
    const session = {
      user: { id: 'duplicate-admin', email: 'admin@example.test' },
      user_id: 'duplicate-admin', context_type: 'regular', active_household_id: 'duplicate-household',
      role: 'admin', display_role: 'admin', permissions: { 'article.create': true },
    }
    await page.route('**/api/**', async (route) => {
      const request = route.request()
      const path = new URL(request.url()).pathname
      if (request.method() !== 'GET') writes.push(path)
      let body = { items: [] }
      if (path === '/api/session') body = session
      if (path === '/api/household') body = { ...session, id: 'duplicate-household' }
      if (path === '/api/receipts') body = { items: ['active', 'rejected'].includes(state) ? [receipt] : [] }
      if (path === '/api/receipts/duplicate-receipt') body = receipt
      if (path === '/api/receipts/import') body = {
        duplicate: true, receipt_table_id: receipt.id,
        duplicate_reason: state === 'archived' ? 'archived' : undefined,
        duplicate_message: state === 'archived' ? 'Deze kassabon staat in Archief.' : 'Deze bon is al ingelezen.',
      }
      await route.fulfill({ json: body })
    })
    if (source === 'share') {
      await page.goto('/kassa?share_status=success&duplicate=1&receipt_table_id=duplicate-receipt')
    } else {
      await page.goto('/kassa/nieuw')
      await page.getByTestId('kassa-manual-file-input').setInputFiles({
        name: 'duplicate.jpg', mimeType: 'image/jpeg', buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
      })
    }
    if (['active', 'rejected'].includes(state)) {
      await expect(page.getByTestId('kassa-duplicate-overlay')).toContainText('De bestaande kassabon is geopend in Kassa.')
      await expect(page).toHaveURL(/\/kassa$/)
      await expect(page.getByTestId('kassa-row-duplicate-receipt')).toBeVisible()
      await expect(page.getByTestId('kassa-row-duplicate-receipt').getByRole('checkbox')).toBeChecked()
      await expect(page.getByTestId('receipt-detail-page')).toBeVisible()
    } else if (state === 'archived') {
      await expect(page.getByRole('dialog')).toContainText('Kassabon staat in Archief')
      await expect(page.getByTestId('kassa-duplicate-overlay')).toHaveCount(0)
    } else {
      await expect(page.getByTestId('kassa-duplicate-overlay')).toContainText(state === 'processed'
        ? 'Deze kassabon is al ingelezen en verwerkt en staat in Voorraad.'
        : 'Deze kassabon is al ingelezen en goedgekeurd en staat in Uitpakken.')
      await expect(page.getByTestId('kassa-duplicate-overlay')).not.toContainText('in Kassa')
      await expect(page).toHaveURL(source === 'share' ? /\/kassa$/ : /\/kassa\/nieuw$/)
      await expect(page.getByTestId('kassa-row-duplicate-receipt')).toHaveCount(0)
      await expect(page.getByTestId('receipt-detail-page')).toHaveCount(0)
    }
    expect(writes).toEqual(source === 'share' ? [] : ['/api/receipts/import'])
  })
}
