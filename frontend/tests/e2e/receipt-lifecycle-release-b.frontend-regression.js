import { test, expect } from '@playwright/test'

async function mockUitpakkenLifecycle(page, { actionResult = {} } = {}) {
  const calls = []

  await page.route('**/api/household', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '0',
        active_household_id: '0',
        role: 'admin',
        display_role: 'admin',
        current_user_display_role: 'admin',
      }),
    })
  })

  await page.route('**/api/unpack-start-batches*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          batch_id: 'release-b-batch',
          receipt_table_id: 'release-b-receipt',
          store_provider_code: 'lidl',
          store_label: 'Lidl',
          purchase_date: '2026-08-14',
          inbox_status: 'Gecontroleerd',
          summary: { total: 2 },
        }],
      }),
    })
  })

  await page.route('**/api/purchase-import-batches/release-b-batch/receipt-lifecycle', async (route) => {
    calls.push({
      url: route.request().url(),
      method: route.request().method(),
      body: route.request().postDataJSON(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', ...actionResult }),
    })
  })

  await page.route('**/api/receipts/delete', async (route) => {
    calls.push({
      url: route.request().url(),
      method: route.request().method(),
      body: route.request().postDataJSON(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', deleted: 1, reimport_allowed: true }),
    })
  })

  return calls
}

async function openDeleteChoice(page) {
  await page.goto('/kassabonnen')
  await expect(page.getByTestId('receipt-batch-row-release-b-batch')).toBeVisible()
  await page.getByTestId('receipt-batch-row-release-b-batch').click()
  await page.getByRole('button', { name: 'Verwijderen', exact: true }).click()
  const dialog = page.getByTestId('unpack-delete-choice-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Terugzetten naar Kassa', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Archiveren', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Volledig verwijderen', exact: true })).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Annuleren', exact: true })).toBeVisible()
  return dialog
}

test.describe('Receipt lifecycle Release B frontend-regressie', () => {
  test('Uitpakken toont exact de drie lifecyclekeuzes plus annuleren', async ({ page }) => {
    await mockUitpakkenLifecycle(page)
    const dialog = await openDeleteChoice(page)
    await expect(dialog.getByRole('button')).toHaveCount(4)
  })

  test('Terugzetten naar Kassa gebruikt uitsluitend lifecycle action return_to_kassa', async ({ page }) => {
    const calls = await mockUitpakkenLifecycle(page)
    const dialog = await openDeleteChoice(page)
    await dialog.getByRole('button', { name: 'Terugzetten naar Kassa', exact: true }).click()

    await expect.poll(() => calls.length).toBe(1)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toContain('/receipt-lifecycle')
    expect(calls[0].body).toEqual({ action: 'return_to_kassa' })
    await expect(page.getByTestId('receipt-batch-row-release-b-batch')).toHaveCount(0)
  })

  test('Archiveren gebruikt uitsluitend lifecycle action archive', async ({ page }) => {
    const calls = await mockUitpakkenLifecycle(page)
    const dialog = await openDeleteChoice(page)
    await dialog.getByRole('button', { name: 'Archiveren', exact: true }).click()

    await expect.poll(() => calls.length).toBe(1)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toContain('/receipt-lifecycle')
    expect(calls[0].body).toEqual({ action: 'archive' })
    await expect(page.getByTestId('receipt-batch-row-release-b-batch')).toHaveCount(0)
  })

  test('Volledig verwijderen gebruikt veilige Kassa-delete met receipt identity', async ({ page }) => {
    const calls = await mockUitpakkenLifecycle(page)
    const dialog = await openDeleteChoice(page)
    await dialog.getByRole('button', { name: 'Volledig verwijderen', exact: true }).click()

    await expect.poll(() => calls.length).toBe(1)
    expect(calls[0].method).toBe('POST')
    expect(calls[0].url).toContain('/api/receipts/delete')
    expect(calls[0].body).toEqual({ receipt_table_ids: ['release-b-receipt'] })
    await expect(page.getByTestId('receipt-batch-row-release-b-batch')).toHaveCount(0)
  })

  test('Gearchiveerde herimport toont precies één dialoog en Admin kan herstellen', async ({ page }) => {
    let restoreCalls = 0

    await page.route('**/api/household', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '0',
          active_household_id: '0',
          role: 'admin',
          display_role: 'admin',
          current_user_display_role: 'admin',
          permissions: { 'article.create': true },
        }),
      })
    })

    await page.route('**/api/receipts/import', async (route) => {
      expect(route.request().method()).toBe('POST')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          duplicate: true,
          duplicate_reason: 'archived',
          duplicate_message: 'Deze kassabon staat in Archief en kan niet opnieuw worden ingelezen. Een beheerder kan de bon terugzetten naar Kassa.',
          receipt_table_id: 'archived-release-b-receipt',
          existing_receipt: { receipt_table_id: 'archived-release-b-receipt' },
        }),
      })
    })

    await page.route('**/api/admin/receipts/archived-release-b-receipt/restore-archived', async (route) => {
      restoreCalls += 1
      expect(route.request().method()).toBe('POST')
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          receipt_table_id: 'archived-release-b-receipt',
          workflow_state: 'returned_to_kassa',
          restored_to: 'kassa',
        }),
      })
    })

    await page.goto('/kassa/nieuw')
    await expect(page.getByTestId('kassa-manual-file-input')).toBeVisible()
    await page.getByTestId('kassa-manual-file-input').setInputFiles({
      name: 'archived-release-b.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    })

    const dialogs = page.getByRole('dialog')
    await expect(dialogs).toHaveCount(1)
    const dialog = dialogs.first()
    await expect(dialog.getByText('Kassabon staat in Archief', { exact: true })).toBeVisible()
    await expect(dialog.getByText(/Deze kassabon staat in Archief/)).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Sluiten', exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Terugzetten uit Archief', exact: true })).toBeVisible()
    await expect(page.getByText('Let op', { exact: true })).toHaveCount(0)

    await dialog.getByRole('button', { name: 'Terugzetten uit Archief', exact: true }).click()
    await expect.poll(() => restoreCalls).toBe(1)
    await expect(dialogs).toHaveCount(0)
  })
})
