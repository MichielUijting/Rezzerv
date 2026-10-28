import { test, expect } from '@playwright/test';

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('Externe databases 2: veilige bulkselectie, export en OFF-ontkoppeling', () => {
  for (const width of [390, 1280]) {
    test(`selectie over pagina's, bevestiging en statusverversing op ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      let rows = Array.from({ length: 12 }, (_, index) => ({
        id: `receipt-table-line:bulk-${index}`, receipt_line_text: `Artikel ${String(index).padStart(2, '0')}`,
        retailer_code: 'jumbo', receipt_article_number: String(index),
        article_code: '8720326035617', quantity_label: '1 stuk',
        link_status: 'linked', off_link_id: `off-link-${index}`,
      }))
      const writes = []
      await page.route('**/api/**', async (route) => {
        const path = new URL(route.request().url()).pathname
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
          items: rows, total: rows.length,
          counts: { unlinked: rows.filter((r) => r.link_status === 'unlinked').length,
            classification_pending: 0, linked: rows.filter((r) => r.link_status === 'linked').length },
        } })
        if (path === '/api/external-databases/off/unlink-selected') {
          const body = route.request().postDataJSON()
          writes.push(body)
          const ids = body.selections.map((item) => item.receipt_item_id)
          rows = rows.map((row) => ids.includes(row.id)
            ? { ...row, link_status: 'unlinked', article_code: '', off_link_id: '' } : row)
          return route.fulfill({ json: { ok: true, unlinked_articles: ids.length, unlinked_links: ids.length } })
        }
        return route.fulfill({ json: { results: [] } })
      })

      await page.goto('/externe-databases-2')
      const table = page.getByTestId('external-databases-2-table')
      await expect(table.locator('tbody tr')).toHaveCount(10)
      await expect(page.getByRole('button', { name: 'Ontkoppelen', exact: true })).toBeDisabled()
      await page.getByLabel('Alles op pagina').check()
      await expect(page.getByText('Geselecteerd: 10')).toBeVisible()
      // Selectie mag het OFF-kandidaatpaneel niet onbedoeld openen.
      await expect(page.getByRole('button', { name: 'Zelf zoeken in OFF' })).toHaveCount(0)
      await page.getByRole('navigation', { name: 'Paginering' }).getByRole('button', { name: '+', exact: true }).click()
      await expect(table.locator('tbody tr')).toHaveCount(2)
      await page.getByLabel('Alles op pagina').check()
      await expect(page.getByText('Geselecteerd: 12')).toBeVisible()
      await page.getByRole('button', { name: 'Ontkoppelen', exact: true }).click()
      await expect(page.getByRole('alertdialog')).toContainText('12 bonartikel(en)')
      await page.getByRole('button', { name: 'Annuleren' }).click()
      expect(writes).toHaveLength(0)
      await page.getByRole('button', { name: 'Ontkoppelen', exact: true }).click()
      await page.getByRole('alertdialog').getByRole('button', { name: 'OK' }).click()
      await expect(page.getByTestId('external-off-link-outcome')).toContainText('12 bonartikel(en) ontkoppeld')
      await expect(page.getByRole('button', { name: 'Niet gekoppeld: 12' })).toBeVisible()
      expect(writes).toHaveLength(1)
      expect(writes[0].selections).toHaveLength(12)
      expect(writes[0].selections[0]).toEqual({ receipt_item_id: 'receipt-table-line:bulk-0', link_id: 'off-link-0' })
      await expect(page.getByRole('button', { name: 'Ontkoppelen', exact: true })).toBeDisabled()
    })
  }

  test('exporteert alleen geselecteerde bonartikelen en houdt formulierdata veilig', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    const articles = [
      { id: 'receipt-table-line:formula', receipt_line_text: '=HYPERLINK("evil")', retailer_code: 'lidl',
        receipt_article_number: '42', article_code: '', link_status: 'unlinked', off_link_id: '' },
      { id: 'receipt-table-line:other', receipt_line_text: 'Andere melk', retailer_code: 'jumbo',
        receipt_article_number: '43', article_code: '8720326035617', link_status: 'linked', off_link_id: 'link-other' },
    ]
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/session') return route.fulfill({ json: {
        user_id: 'test-superuser', active_household_id: '0', context_type: 'system',
        role: 'owner', is_platform_superuser: true,
        permissions: { 'platform.system_household.access': true },
      } })
      if (path === '/api/maintenance/status') return route.fulfill({ json: { state: 'normal' } })
      if (path === '/api/external-databases/articles-overview') return route.fulfill({ json: {
        items: articles, total: 2, counts: { unlinked: 1, linked: 1, classification_pending: 0 },
      } })
      return route.fulfill({ json: {} })
    })
    await page.goto('/externe-databases-2')
    const exportButton = page.getByRole('button', { name: 'Exporteren', exact: true })
    await expect(exportButton).toBeDisabled()
    await page.getByRole('checkbox', { name: 'Selecteer =HYPERLINK("evil")' }).check()
    await expect(page.getByRole('button', { name: 'Ontkoppelen', exact: true })).toBeDisabled()
    const downloadPromise = page.waitForEvent('download')
    await exportButton.click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe('inhuis-externe-databases-2-artikelen.csv')
    const { readFile } = await import('node:fs/promises')
    const csv = await readFile(await download.path(), 'utf8')
    expect(csv).toContain("'=HYPERLINK")
    expect(csv).not.toContain('Andere melk')
  })
})
