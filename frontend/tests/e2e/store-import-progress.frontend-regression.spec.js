import { expect, test } from '@playwright/test'

async function mockStorePage(page) {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const responses = {
      '/api/session': {
        authenticated: true, user: { id: 'progress-admin', email: 'progress@example.test' },
        user_id: 'progress-admin', email: 'progress@example.test', context_type: 'regular',
        active_household_id: 'progress-household', active_household_name: 'Test huishouden',
        role: 'admin', display_role: 'admin', household_role: 'household.admin',
        permissions: { 'household_settings.manage': true },
        supported_permissions: ['household_settings.manage'], is_viewer: false,
        is_platform_superuser: false, is_frontteam: false,
      },
      '/api/session/households': { items: [], can_switch_households: false },
      '/api/household': { id: 'progress-household', name: 'Test huishouden' },
      '/api/store-providers': [{ code: 'ah', name: 'Albert Heijn' }, { code: 'jumbo', name: 'Jumbo' }],
      '/api/store-connections': [],
      '/api/receipts/retailers/ah/status': { connected: true },
      '/api/receipts/retailers/lidl/import-window': { from_date: '2026-10-01', to_date: '2026-10-31', can_manage: false },
      '/api/maintenance/status': { state: 'normal' },
    }
    return route.fulfill({ json: responses[path] ?? {} })
  })
}

const payload = {
  version: 14, ok: true, source_origin: 'https://www.jumbo.com', total_results: 2,
  details: [1, 2].map(n => ({
    transactionId: `TEST:receipt-${n}.json`, purchaseEndOn: '2026-10-19 13:24:35', storeName: 'Jumbo Test',
    parsed: { items: [{ name: 'KOFFIE', quantity: 1, unitPrice: 2, price: 2 }], deposits: [], total: 2 },
  })),
}
const previewUrl = '/instellingen/winkelkoppelingen#jumbo-poc-v14=' + encodeURIComponent(JSON.stringify(payload))

for (const width of [1280, 390]) {
  test(`Jumbo counts confirmed receipts and retains concise UI at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockStorePage(page)
    let calls = 0
    let release
    await page.route('**/api/receipts/retailers/import', async route => {
      calls += 1
      if (calls === 2) await new Promise(resolve => { release = resolve })
      await route.fulfill({ json: { duplicate: calls === 2, raw_receipt_id: `test-${calls}` } })
    })
    await page.goto(previewUrl)
    const preview = page.getByTestId('jumbo-poc-result')
    await expect(preview).toBeVisible()
    expect(calls).toBe(0)
    await expect(preview).not.toContainText('TEST:receipt')
    await expect(page.getByTestId('jumbo-bookmarklet-help')).not.toHaveAttribute('open', '')
    await page.getByTestId('jumbo-confirm-import').click()
    const status = page.getByTestId('jumbo-poc-progress')
    await expect(status).toHaveAttribute('role', 'status')
    await expect(status).toContainText('1 van 2 bonnen verwerkt')
    await expect(status.getByRole('progressbar')).toHaveAttribute('value', '1')
    await expect(page.getByTestId('jumbo-confirm-import')).toBeDisabled()
    await expect.poll(() => typeof release).toBe('function')
    release()
    await expect(status).toContainText('Afgerond')
    await expect(status).toContainText('2 van 2 bonnen verwerkt')
    await expect(status).toContainText('1 nieuw · 1 bekend · 0 bijgewerkt · 0 mislukt')
    await expect(preview).toHaveCount(0)
    expect(calls).toBe(2)
  })
}

test('Jumbo retains confirmed count after a later receipt fails', async ({ page }) => {
  await mockStorePage(page)
  let calls = 0
  await page.route('**/api/receipts/retailers/import', route => {
    calls += 1
    return calls === 1
      ? route.fulfill({ json: { duplicate: false, raw_receipt_id: 'test-first' } })
      : route.fulfill({ status: 503, json: { detail: 'Testverbinding onderbroken' } })
  })
  await page.goto(previewUrl)
  await page.getByTestId('jumbo-confirm-import').click()
  const status = page.getByTestId('jumbo-poc-progress')
  await expect(status).toContainText('Mislukt')
  await expect(status).toContainText('1 van 2 bonnen verwerkt')
  await expect(status).toContainText('1 nieuw · 0 bekend · 0 bijgewerkt · 1 mislukt')
  await expect(page.getByTestId('jumbo-poc-result')).toBeVisible()
  await expect(page.getByTestId('jumbo-confirm-import')).toBeEnabled()
})

test('AH shows waiting status without an invented progress total', async ({ page }) => {
  await mockStorePage(page)
  let release
  await page.route('**/api/receipts/retailers/ah/sync', async route => {
    await new Promise(resolve => { release = resolve })
    await route.fulfill({ json: { receipts_found: 3, receipts_processed: 2, receipts_skipped_known: 1, receipts_failed: 0 } })
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-ah').click()
  await page.getByTestId('ah-sync-receipts').click()
  const status = page.getByTestId('ah-sync-progress')
  await expect(status).toContainText('Bonnen ophalen')
  await expect(status.getByRole('progressbar')).toHaveCount(0)
  await expect(page.getByTestId('ah-sync-progress-counter')).toHaveCount(0)
  await expect.poll(() => typeof release).toBe('function')
  release()
  await expect(status).toContainText('Afgerond')
  await expect(status).toContainText('2 nieuw · 1 bekend · 0 bijgewerkt · 0 mislukt')
})

for (const receiptId of ['123456789012', 'TEST:LIDL']) {
  test(`Lidl shows rejection immediately for ${receiptId}`, async ({ page }) => {
    await mockStorePage(page)
    await page.route('**/api/receipts/retailers/import', route => route.fulfill({ json: {} }))
    await page.goto('/instellingen/winkelkoppelingen')
    await page.getByTestId('receipt-connection-action-lidl').click()
    await expect(page.getByTestId('lidl-digital-receipts')).toBeVisible()
    await page.evaluate(() => window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://www.lidl.nl', source: window,
      data: { type: 'inhuis:lidl-handshake', bookmarklet_version: 2 },
    })))
    const status = page.getByTestId('lidl-web-progress')
    await expect(status).toContainText('Bonnen ophalen')
    await page.evaluate(id => window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://www.lidl.nl', source: window,
      data: { type: 'inhuis:lidl-receipt', receipt: {
        id, products: [{ name: 'KOFFIE', quantity: 1, price: 2 }],
      } },
    })), receiptId)
    await expect(status).toContainText('Mislukt')
    await expect(status).toContainText('0 nieuw · 0 bekend · 0 bijgewerkt · 1 mislukt')
    await expect(status.getByRole('progressbar')).toHaveCount(0)
  })
}

for (const width of [1280, 390]) {
  test(`Digital receipt setup is visible first with honest capabilities at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockStorePage(page)
    await page.goto('/instellingen/winkelkoppelingen')
    const overview = page.getByTestId('receipt-connections-overview-table')
    await expect(overview).toBeVisible()
    await expect(page.getByTestId('receipt-connection-summary')).toContainText('1 gekoppeld')
    await expect(page.getByTestId('receipt-connection-mode-ah')).toContainText('Automatisch bij Kassa')
    await expect(page.getByTestId('receipt-connection-status-ah')).toContainText('Gekoppeld')
    await expect(page.getByTestId('receipt-connection-mode-jumbo')).toContainText('Via browser')
    await expect(page.getByTestId('receipt-connection-status-jumbo')).toContainText('Browserstap nodig')
    await expect(page.getByTestId('receipt-connection-status-aldi')).toContainText('Nog niet beschikbaar')
    await expect(page.getByTestId('jumbo-receipt-poc')).toHaveCount(0)
    await expect(page.getByTestId('ah-digital-receipts')).toHaveCount(0)
    await page.getByTestId('receipt-connection-action-jumbo').click()
    await expect(page.getByTestId('jumbo-receipt-poc')).toBeVisible()
    await expect(page.getByTestId('jumbo-bookmarklet-help')).not.toHaveAttribute('open', '')
    await page.getByTestId('receipt-connection-action-ah').click()
    await expect(page.getByTestId('ah-digital-receipts')).toBeVisible()
    await expect(page.getByTestId('jumbo-receipt-poc')).toHaveCount(0)
  })
}
