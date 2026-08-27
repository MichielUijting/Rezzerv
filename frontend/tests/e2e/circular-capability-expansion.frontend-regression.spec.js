import { test, expect } from '@playwright/test'

function uniqueEmail() {
  return `circular-expansion-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`
}

async function completeInhuisHalenOnboarding(page, householdName = 'Circulaire uitbreiding test') {
  const email = uniqueEmail()
  const password = 'SterkWachtwoord123!'

  const registration = await page.request.post('/api/auth/register', {
    data: { email, password },
  })
  expect(registration.status()).toBe(201)

  expect((await page.request.post('/api/onboarding/primary-use-case', {
    data: { primary_use_case: 'inhuis_halen' },
  })).ok()).toBeTruthy()

  expect((await page.request.post('/api/onboarding/inhuis-halen', {
    data: {
      simple_inventory_enabled: true,
      almost_out_notifications_enabled: true,
      receipt_processing_enabled: true,
      recipes_enabled: false,
    },
  })).ok()).toBeTruthy()

  expect((await page.request.post('/api/onboarding/shared-household-minimum', {
    data: {
      household_name: householdName,
      household_usage_mode: 'alone',
    },
  })).ok()).toBeTruthy()

  return { email, password }
}

test('Inhuis halen can add Wat Inhuis without rerunning or downgrading existing configuration', async ({ page }) => {
  await completeInhuisHalenOnboarding(page)

  const before = await page.request.get('/api/onboarding/capabilities')
  expect(before.ok()).toBeTruthy()
  const beforePayload = await before.json()
  expect(beforePayload.primary_use_case).toBe('inhuis_halen')
  expect(beforePayload.active_use_cases).toEqual(['inhuis_halen'])
  expect(beforePayload.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(beforePayload.product_configuration.shopping_enabled).toBe(true)
  expect(beforePayload.product_configuration.receipt_processing_enabled).toBe(true)

  await page.goto('/instellingen/mogelijkheden')
  await expect(page.getByTestId('settings-capabilities-page')).toBeVisible()
  await expect(page.getByTestId('capability-active-inhuis_halen')).toBeVisible()
  await page.getByTestId('capability-add-wat_inhuis').click()

  await expect(page.getByTestId('capability-expansion-form-wat_inhuis')).toBeVisible()
  await expect(page.getByTestId('capability-wat-global-locations')).toBeVisible()
  await expect(page.getByTestId('capability-wat-inventory-level')).toHaveCount(0)
  await expect(page.getByTestId('capability-wat-almost-out')).toHaveCount(0)
  await expect(page.getByTestId('capability-wat-shopping')).toHaveCount(0)

  await page.getByTestId('capability-wat-global-locations').check()
  await page.getByTestId('capability-expansion-submit').click()
  await expect(page.getByTestId('capability-active-wat_inhuis')).toBeVisible()

  const after = await page.request.get('/api/onboarding/capabilities')
  expect(after.ok()).toBeTruthy()
  const afterPayload = await after.json()
  expect(afterPayload.primary_use_case).toBe('inhuis_halen')
  expect(afterPayload.active_use_cases).toEqual(['inhuis_halen', 'wat_inhuis'])
  expect(afterPayload.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(afterPayload.product_configuration.location_tracking_level).toBe('global')
  expect(afterPayload.product_configuration.shopping_enabled).toBe(true)
  expect(afterPayload.product_configuration.almost_out_enabled).toBe(true)
  expect(afterPayload.product_configuration.almost_out_notifications_enabled).toBe(true)
  expect(afterPayload.product_configuration.receipt_processing_enabled).toBe(true)

  await page.goto('/instellingen')
  await expect(page.getByTestId('settings-tile-capabilities')).toBeVisible()
  await expect(page.getByTestId('settings-tile-locations')).toBeVisible()
})

test('later activating Waar Inhuis preserves and partially assigns existing locationless stock', async ({ page }) => {
  await completeInhuisHalenOnboarding(page, 'Waar Inhuis overgangstest')

  const purchase = await page.request.post('/api/inventory-events', {
    data: {
      article_name: 'Pasta overgangstest',
      quantity: 5,
      event_type: 'purchase',
      note: 'Locatieloze voorraad vóór activeren Waar Inhuis',
    },
  })
  expect(purchase.ok()).toBeTruthy()

  const beforePreviewResponse = await page.request.get('/api/dev/inventory-preview')
  expect(beforePreviewResponse.ok()).toBeTruthy()
  const beforePreview = await beforePreviewResponse.json()
  const beforeRow = beforePreview.rows.find((row) => row.artikel === 'Pasta overgangstest')
  expect(beforeRow).toBeTruthy()
  expect(beforeRow.aantal).toBe(5)
  expect(beforeRow.space_id).toBeNull()
  expect(beforeRow.sublocation_id).toBeNull()
  const inventoryId = String(beforeRow.id)
  const householdArticleId = String(beforeRow.household_article_id)
  expect(inventoryId).not.toBe('')
  expect(householdArticleId).not.toBe('')

  await page.goto('/instellingen/mogelijkheden')
  await page.getByTestId('capability-add-waar_inhuis').click()
  await expect(page.getByTestId('capability-expansion-form-waar_inhuis')).toBeVisible()
  await expect(page.getByTestId('capability-waar-main-location-0')).toHaveCount(0)
  await page.getByTestId('capability-expansion-submit').click()
  await expect(page.getByTestId('capability-active-waar_inhuis')).toBeVisible()

  const capabilitiesResponse = await page.request.get('/api/onboarding/capabilities')
  expect(capabilitiesResponse.ok()).toBeTruthy()
  const capabilities = await capabilitiesResponse.json()
  expect(capabilities.active_use_cases).toContain('waar_inhuis')
  expect(capabilities.product_configuration.inventory_tracking_level).toBe('quantity')
  expect(capabilities.product_configuration.location_tracking_level).toBe('exact')

  const preservedPreviewResponse = await page.request.get('/api/dev/inventory-preview')
  expect(preservedPreviewResponse.ok()).toBeTruthy()
  const preservedPreview = await preservedPreviewResponse.json()
  const preservedRow = preservedPreview.rows.find((row) => row.id === inventoryId)
  expect(preservedRow).toBeTruthy()
  expect(preservedRow.aantal).toBe(5)
  expect(preservedRow.space_id).toBeNull()
  expect(preservedRow.sublocation_id).toBeNull()

  const createSpace = await page.request.post('/api/spaces', {
    data: { naam: 'Keuken overgangstest' },
  })
  expect(createSpace.ok()).toBeTruthy()

  await page.goto(`/voorraad/${encodeURIComponent(householdArticleId)}?tab=${encodeURIComponent('Voorraad')}`)
  await expect(page.getByTestId('article-detail-page')).toBeVisible()
  await expect(page.getByTestId(`article-stock-unassigned-${inventoryId}`)).toHaveText('Nog geen locatie')

  await page.getByTestId(`article-stock-assign-location-${inventoryId}`).click()
  await expect(page.getByTestId('article-stock-location-assignment-form')).toBeVisible()
  await page.getByLabel('Aantal toewijzen').fill('2')
  await page.getByTestId('article-stock-assignment-space').selectOption({ label: 'Keuken overgangstest' })
  await page.getByTestId('article-stock-location-assignment-form').getByRole('button', { name: 'Toewijzen', exact: true }).click()
  await expect(page.getByTestId('article-stock-mutation-success')).toContainText('2 toegewezen aan Keuken overgangstest')

  const afterPreviewResponse = await page.request.get('/api/dev/inventory-preview')
  expect(afterPreviewResponse.ok()).toBeTruthy()
  const afterPreview = await afterPreviewResponse.json()
  const articleRows = afterPreview.rows.filter((row) => row.household_article_id === householdArticleId)
  const remainingUnassigned = articleRows.find((row) => row.space_id == null && row.sublocation_id == null)
  const assigned = articleRows.find((row) => row.locatie === 'Keuken overgangstest')

  expect(remainingUnassigned).toBeTruthy()
  expect(remainingUnassigned.aantal).toBe(3)
  expect(assigned).toBeTruthy()
  expect(assigned.aantal).toBe(2)
  expect(articleRows.reduce((sum, row) => sum + Number(row.aantal || 0), 0)).toBe(5)

  const historyResponse = await page.request.get(`/api/household-articles/${encodeURIComponent(householdArticleId)}/events`)
  expect(historyResponse.ok()).toBeTruthy()
  const history = await historyResponse.json()
  expect(history.items.some((item) => item.event_type === 'transfer_out')).toBeTruthy()
  expect(history.items.some((item) => item.event_type === 'transfer_in')).toBeTruthy()
})
