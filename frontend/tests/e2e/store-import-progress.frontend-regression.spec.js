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
      '/api/receipts/retailers/lidl/import-window': { from_date: '2026-10-01', to_date: '2026-10-31', can_manage: true },
      '/api/receipts/retailers/last-updated': { dates: { jumbo: '2026-10-19', lidl: '2026-10-21' } },
      '/api/maintenance/status': { state: 'normal' },
    }
    return route.fulfill({ json: responses[path] ?? {} })
  })
}

async function receiptPanelGeometry(page, provider) {
  return page.evaluate(store => {
    const root = document.querySelector(store === 'jumbo'
      ? '[data-testid="jumbo-receipt-poc"]'
      : '[data-testid="lidl-digital-receipts"]')
    if (!root) throw new Error('Receipt panel not mounted')
    const base = root.getBoundingClientRect()
    const box = (selector) => {
      const element = root.querySelector(selector)
      if (!element) throw new Error('Missing matching panel element: ' + selector)
      const rect = element.getBoundingClientRect()
      return [rect.x - base.x, rect.y - base.y, rect.width, rect.height]
        .map(value => Math.round(value))
    }
    return {
      panel: [Math.round(base.width), Math.round(base.height)],
      heading: box('h3'),
      description: box('p:last-child'),
      from: box('input[data-testid$="-from-date"]'),
      to: box('input[data-testid$="-to-date"]'),
      actions: box('[data-testid="retailer-receipt-action-row"]'),
      open: box(store === 'jumbo' ? '[data-testid="jumbo-poc-open"]' : '[data-testid="lidl-web-open-history"]'),
      help: box(store === 'jumbo' ? '[data-testid="jumbo-help-open"]' : '[data-testid="lidl-help-open"]'),
    }
  }, provider)
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
    await expect(page.getByTestId('jumbo-bookmarklet-dialog')).toHaveCount(0)
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

for (const width of [1280, 896, 390]) {
  test(`Digital receipt setup is visible first with honest capabilities at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockStorePage(page)
    await page.goto('/instellingen/winkelkoppelingen')
    const overview = page.getByTestId('receipt-connections-overview-table')
    await expect(overview).toBeVisible()
    await expect(page.getByTestId('receipt-connection-summary')).toHaveCount(0)
    await expect(overview.locator('thead th')).toHaveText(['Winkel', 'Laatst bijgewerkt', 'Status'])
    await expect(page.getByTestId('receipt-connection-updated-ah')).not.toBeEmpty()
    await expect(page.getByTestId('receipt-connection-updated-jumbo')).toHaveText('19-10-2026')
    await expect(page.getByTestId('receipt-connection-updated-lidl')).toHaveText('21-10-2026')
    await expect(page.getByTestId('receipt-connection-action-ah')).toHaveText('Bekijken')
    await expect(page.getByTestId('receipt-connection-action-jumbo')).toHaveText('Bonnen ophalen')
    await expect(page.getByTestId('receipt-connection-action-lidl')).toHaveText('Bonnen ophalen')
    await expect(page.getByTestId('receipt-connection-status-aldi')).toContainText('Geen koppeling mogelijk')
    await expect(page.getByTestId('receipt-connection-status-plus')).toContainText('Geen koppeling mogelijk')
    await expect(page.getByTestId('loyalty-connections-settings')).toHaveCount(0)
    await expect(page.getByTestId('jumbo-receipt-poc')).toHaveCount(0)
    await expect(page.getByTestId('ah-digital-receipts')).toHaveCount(0)
    for (const code of ['aldi', 'plus']) {
      await expect(page.getByTestId('receipt-connection-action-' + code)).toHaveCount(0)
      const unavailable = page.getByTestId('receipt-connection-unavailable-' + code)
      await expect(unavailable).toHaveText('Geen koppeling mogelijk')
      await expect(unavailable).toHaveAttribute('title', /geen digitale kassabonnen aan via haar website of klantenpas/)
      await expect(unavailable.locator('button')).toHaveCount(0)
      await expect(unavailable).toHaveCSS('color', /^rgb/)
    }
    await expect(page.getByTestId('aldi-digital-unavailable')).toHaveCount(0)
    const overviewCard = overview.locator('xpath=ancestor::*[contains(@class, "rz-card")][1]')
    const beforeClick = await overviewCard.boundingBox()
    await page.getByTestId('receipt-connection-action-jumbo').click()
    const jumbo = page.getByTestId('jumbo-receipt-poc')
    await expect(jumbo).toBeVisible()
    await expect(page.getByTestId('jumbo-from-date')).toHaveValue('2026-10-19')
    const detailsCard = jumbo.locator('xpath=ancestor::*[contains(@class, "rz-card")][1]')
    const afterClick = await overviewCard.boundingBox()
    const details = await detailsCard.boundingBox()
    expect(Math.abs(beforeClick.width - afterClick.width)).toBeLessThan(2)
    expect(Math.abs(beforeClick.width - details.width)).toBeLessThan(2)
    const jumboGeometry = await receiptPanelGeometry(page, 'jumbo')

    const openJumbo = page.getByTestId('jumbo-poc-open')
    const firstTime = page.getByTestId('jumbo-help-open')
    const openBox = await openJumbo.boundingBox()
    const firstTimeBox = await firstTime.boundingBox()
    expect(Math.abs(openBox.y - firstTimeBox.y)).toBeLessThan(2)
    expect(firstTimeBox.x).toBeGreaterThan(openBox.x)
    await firstTime.click()
    const dialog = page.getByTestId('jumbo-bookmarklet-dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(page.getByTestId('jumbo-poc-bookmarklet')).toHaveAttribute('draggable', 'true')
    await expect(page.getByTestId('jumbo-poc-bookmarklet')).toHaveAttribute('href', /^javascript:/)
    await page.keyboard.press('Escape')
    await expect(dialog).toBeVisible()
    await page.mouse.click(5, 5)
    await expect(dialog).toBeVisible()
    await page.getByTestId('jumbo-help-ok').click()
    await expect(dialog).toHaveCount(0)
    await page.getByTestId('receipt-connection-action-lidl').click()
    await expect(page.getByTestId('lidl-digital-receipts')).toBeVisible()
    await expect(page.getByTestId('lidl-from-date')).toHaveValue('2026-10-21')
    await expect(page.getByTestId('lidl-to-date')).not.toHaveValue('')
    const lidlCard = page.getByTestId('lidl-digital-receipts').locator('xpath=ancestor::*[contains(@class, "rz-card")][1]')
    const lidlDimensions = await lidlCard.boundingBox()
    expect(Math.abs(beforeClick.width - lidlDimensions.width)).toBeLessThan(2)
    const lidlGeometry = await receiptPanelGeometry(page, 'lidl')
    expect(lidlGeometry).toEqual(jumboGeometry)

    const lidlOpen = await page.getByTestId('lidl-web-open-history').boundingBox()
    const lidlHelp = await page.getByTestId('lidl-help-open').boundingBox()
    expect(Math.abs(lidlOpen.y - lidlHelp.y)).toBeLessThan(2)
    expect(lidlHelp.x).toBeGreaterThan(lidlOpen.x)
    await page.getByTestId('lidl-help-open').click()
    const lidlDialog = page.getByTestId('lidl-bookmarklet-dialog')
    await expect(lidlDialog).toBeVisible()
    await expect(lidlDialog).toHaveAttribute('aria-modal', 'true')
    await expect(page.getByTestId('lidl-web-bookmarklet')).toHaveAttribute('draggable', 'true')
    await expect(page.getByTestId('lidl-web-bookmarklet')).toHaveAttribute('href', /^javascript:/)
    await page.keyboard.press('Escape')
    await expect(lidlDialog).toBeVisible()
    await page.mouse.click(5, 5)
    await expect(lidlDialog).toBeVisible()
    await page.getByTestId('lidl-help-ok').click()
    await expect(lidlDialog).toHaveCount(0)
    await page.getByTestId('receipt-connection-action-ah').click()
    await expect(page.getByTestId('ah-digital-receipts')).toBeVisible()
    await expect(page.getByTestId('jumbo-receipt-poc')).toHaveCount(0)
  })
}

for (const width of [390, 896, 1280]) {
  test(`Winkelpanelen hebben alleen mobiel nul verticale tussenruimte bij ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockStorePage(page)
    await page.goto('/instellingen/winkelkoppelingen')
    const mobile = width <= 720
    for (const [provider, panelId] of [
      ['jumbo', 'jumbo-receipt-poc'],
      ['lidl', 'lidl-digital-receipts'],
      ['ah', 'ah-digital-receipts'],
      ['picnic', 'picnic-account-research'],
    ]) {
      await page.getByTestId('receipt-connection-action-' + provider).click()
      const panel = page.getByTestId(panelId)
      await expect(panel).toBeVisible()
      const layout = await panel.evaluate(element => {
        const computed = window.getComputedStyle(element)
        const firstText = element.querySelector('p')
        const dateRow = element.querySelector('input[type="date"]')?.closest(
          '[data-testid="lidl-import-window"], [data-testid="retailer-receipt-date-range"]',
        )
        const dateLabel = element.querySelector('.rz-input-field')
        return {
          gap: computed.rowGap,
          textMargin: firstText ? window.getComputedStyle(firstText).marginTop : null,
          dateGap: dateRow ? window.getComputedStyle(dateRow).rowGap : null,
          labelGap: dateLabel ? window.getComputedStyle(dateLabel).rowGap : null,
        }
      })
      expect(layout.gap).toBe(mobile ? '0px' : '12px')
      if (provider === 'jumbo' || provider === 'lidl') {
        expect(layout.textMargin).toBe(mobile ? '0px' : '6px')
        expect(layout.labelGap).toBe(mobile ? '0px' : '6px')
        expect(layout.dateGap).toBe(mobile ? '0px' : '12px')
      } else if (provider === 'ah') {
        expect(layout.textMargin).toBe(mobile ? '0px' : '6px')
      }
    }
  })
}

test('Lidl automatically saves changed dates before opening browser and keeps one user action', async ({ page }) => {
  await mockStorePage(page)
  let releaseSave
  let requestedPeriod = null
  await page.route('**/api/receipts/retailers/lidl/import-window', async route => {
    if (route.request().method() === 'PUT') {
      requestedPeriod = route.request().postDataJSON()
      await new Promise(resolve => { releaseSave = resolve })
      return route.fulfill({ json: {
        from_date: '2026-10-21', to_date: '2026-10-31',
        configured_from_date: '2026-10-21', configured_to_date: null,
        can_manage: true,
      } })
    }
    return route.fulfill({ json: {
      from_date: '2026-10-01', to_date: '2026-10-31',
      configured_from_date: null, configured_to_date: null,
      can_manage: true,
    } })
  })
  await page.addInitScript(() => {
    window.__lidlPopupCalls = []
    window.__lidlLaunched = null
    window.__lidlClosed = false
    window.open = (...args) => {
      window.__lidlPopupCalls.push(args)
      return {
        closed: false,
        location: { replace: url => { window.__lidlLaunched = url } },
        close() { this.closed = true; window.__lidlClosed = true },
      }
    }
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await expect(page.getByTestId('lidl-from-date')).toHaveValue('2026-10-21')
  await expect(page.getByTestId('lidl-period-unsaved')).toHaveCount(0)
  await expect(page.getByTestId('lidl-save-period')).toHaveCount(0)
  await expect(page.getByTestId('lidl-reset-period')).toHaveCount(0)
  const open = page.getByTestId('lidl-web-open-history')
  await expect(open).toBeEnabled()
  await open.click()
  await expect(open).toBeDisabled()
  await expect.poll(() => requestedPeriod).toEqual({ from_date: '2026-10-21', to_date: null })
  const beforeSave = await page.evaluate(() => ({
    tabs: window.__lidlPopupCalls, launched: window.__lidlLaunched,
  }))
  expect(beforeSave.tabs).toEqual([['about:blank', '_blank']])
  expect(beforeSave.launched).toBe(null)
  expect(typeof releaseSave).toBe('function')
  releaseSave()
  await expect.poll(() => page.evaluate(() => window.__lidlLaunched)).toContain('www.lidl.nl')
  await expect(open).toBeEnabled()
  expect(await page.evaluate(() => window.__lidlClosed)).toBe(false)
})

test('Lidl does not open retailer or leave stale dates after failed automatic period save', async ({ page }) => {
  await mockStorePage(page)
  let updates = 0
  await page.route('**/api/receipts/retailers/lidl/import-window', route => {
    if (route.request().method() === 'PUT') {
      updates++
      return route.fulfill({ status: 503, json: { detail: 'Opslaan tijdelijk niet beschikbaar.' } })
    }
    return route.fulfill({ json: { from_date: '2026-10-01', to_date: '2026-10-31', can_manage: true } })
  })
  await page.addInitScript(() => {
    window.__lidlOpened = null
    window.__lidlPopupClosed = false
    window.open = () => ({
      closed: false,
      location: { replace: url => { window.__lidlOpened = url } },
      close() { this.closed = true; window.__lidlPopupClosed = true },
    })
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await page.getByTestId('lidl-web-open-history').click()
  await expect.poll(() => updates).toBe(1)
  await expect.poll(() => page.evaluate(() => window.__lidlPopupClosed)).toBe(true)
  expect(await page.evaluate(() => window.__lidlOpened)).toBe(null)
  await expect(page.getByTestId('lidl-from-date')).toHaveValue('2026-10-21')
  await expect(page.getByTestId('lidl-web-open-history')).toBeEnabled()
})

test('Lidl avoids unnecessary saves when date window already matches', async ({ page }) => {
  await mockStorePage(page)
  let updates = 0
  await page.route('**/api/receipts/retailers/lidl/import-window', route => {
    if (route.request().method() === 'PUT') {
      updates++
      return route.fulfill({ status: 500, json: {} })
    }
    return route.fulfill({ json: {
      from_date: '2026-10-21', to_date: '2026-10-31',
      configured_from_date: '2026-10-21', configured_to_date: null,
      can_manage: true,
    } })
  })
  await page.addInitScript(() => {
    window.__lidlOpened = null
    window.open = () => ({
      closed: false,
      location: { replace: url => { window.__lidlOpened = url } },
      close() { this.closed = true },
    })
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await page.getByTestId('lidl-web-open-history').click()
  await expect.poll(() => page.evaluate(() => window.__lidlOpened)).toContain('www.lidl.nl')
  expect(updates).toBe(0)
})

test('Lidl cannot bypass household period permissions or blocked browser popups', async ({ page }) => {
  await mockStorePage(page)
  let updates = 0
  await page.route('**/api/receipts/retailers/lidl/import-window', route => {
    if (route.request().method() === 'PUT') {
      updates++
      return route.fulfill({ status: 403, json: {} })
    }
    return route.fulfill({ json: {
      from_date: '2026-10-01', to_date: '2026-10-31', can_manage: false,
    } })
  })
  await page.addInitScript(() => {
    window.__lidlAttemptedPopup = 0
    window.open = () => { window.__lidlAttemptedPopup++; return null }
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await page.getByTestId('lidl-web-open-history').click()
  expect(updates).toBe(0)
  expect(await page.evaluate(() => window.__lidlAttemptedPopup)).toBe(0)
})

test('Lidl refuses to save a changed period when popup permission is blocked', async ({ page }) => {
  await mockStorePage(page)
  let saves = 0
  await page.route('**/api/receipts/retailers/lidl/import-window', route => {
    if (route.request().method() === 'PUT') {
      saves++
      return route.fulfill({ status: 500, json: {} })
    }
    return route.fulfill({ json: {
      from_date: '2026-10-01', to_date: '2026-10-31', can_manage: true,
    } })
  })
  await page.addInitScript(() => {
    window.__lidlPopupBlocked = true
    window.open = () => null
  })
  await page.goto('/instellingen/winkelkoppelingen')
  await page.getByTestId('receipt-connection-action-lidl').click()
  await page.getByTestId('lidl-web-open-history').click()
  expect(saves).toBe(0)
  await expect(page.getByTestId('lidl-web-open-history')).toBeEnabled()
})
