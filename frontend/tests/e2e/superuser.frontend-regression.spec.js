import { test, expect } from '@playwright/test'

const SUPERUSER_EMAIL = process.env.PLAYWRIGHT_SUPERUSER_EMAIL || 'supergebruiker@rezzerv.local'
const SUPERUSER_PASSWORD = process.env.PLAYWRIGHT_SUPERUSER_PASSWORD

async function loginAsSuperuser(page) {
  if (!SUPERUSER_PASSWORD) throw new Error('PLAYWRIGHT_SUPERUSER_PASSWORD ontbreekt.')
  await page.context().clearCookies()
  await page.goto('/login')
  await page.getByLabel('E-mail').fill(SUPERUSER_EMAIL)
  await page.getByLabel('Wachtwoord').fill(SUPERUSER_PASSWORD)
  await page.getByRole('button', { name: 'Inloggen' }).click()
  await page.waitForURL('**/home')
}

async function expectSortableHeader(table, header) {
  await expect(table.getByRole('button', { name: `${header} sorteren`, exact: true })).toBeVisible()
}

async function expectHorizontalScrollbar(table) {
  const wrapper = table.locator('xpath=ancestor::div[contains(@class,"rz-table-wrapper")]').first()
  await expect(wrapper).toBeVisible()
  const state = await wrapper.evaluate((element) => ({
    overflowX: window.getComputedStyle(element).overflowX,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }))
  expect(state.overflowX).toBe('auto')
  expect(state.scrollWidth).toBeGreaterThan(state.clientWidth)
}

async function horizontalCenter(locator) {
  const box = await locator.boundingBox()
  if (!box) throw new Error('Element heeft geen bounding box.')
  return box.x + (box.width / 2)
}

async function expectReadOnlyInspector(inspector) {
  await expect(inspector.locator('textarea')).toHaveCount(0)
  await expect(inspector.locator('form')).toHaveCount(0)
  const nonCheckboxInputs = inspector.locator('input:not([type="checkbox"])')
  const inputCount = await nonCheckboxInputs.count()
  expect(inputCount).toBeGreaterThan(0)
  const allInputsAreTableFilters = await nonCheckboxInputs.evaluateAll((elements) => elements.every((element) => element.classList.contains('rz-inline-input')))
  expect(allInputsAreTableFilters).toBe(true)
  await expect(inspector.getByRole('button', { name: /^(Opslaan|Bewaren|Toevoegen|Aanmaken|Bewerken|Wijzigen|Verwijderen|Corrigeren|Verwerken)$/i })).toHaveCount(0)
}

test.describe('Superuser frontend-regressie', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperuser(page)
    await page.goto('/superuser')
    await expect(page.getByTestId('superuser-dashboard')).toBeVisible()
  })

  test('beheercentrum bewaakt tabs, huishoudselectie/export en read-only huishoudinzage', async ({ page }) => {
    await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')
    for (const tabName of ['Overzicht', 'Huishoudens', 'Gebruikers', 'Gebruik', 'Kassabonnen', 'Meldingen', 'Systeem']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible()
    }

    await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()
    for (const label of ['Actieve huishoudens', 'Actieve gebruikers', 'Kassabonnen', 'Open meldingen', 'Aandacht vereist']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }

    await page.getByRole('tab', { name: 'Huishoudens', exact: true }).click()
    const householdsSection = page.getByTestId('superuser-households')
    const households = page.getByTestId('superuser-households-table')
    await expect(households).toBeVisible()
    for (const header of ['Huishouden', 'Status', 'Actieve gebruikers', 'Gearchiveerd', 'Aangemaakt op', 'Laatst actief', 'Kassabonnen', 'Open meldingen', 'Aandacht vereist']) {
      await expectSortableHeader(households, header)
    }
    await expectHorizontalScrollbar(households)
    await expect(householdsSection.getByRole('navigation', { name: 'Paginering' })).toBeVisible()

    const selectAllHouseholds = householdsSection.getByLabel('Selecteer alle huishoudens')
    await expect(selectAllHouseholds).toBeVisible()
    await expect(selectAllHouseholds).not.toBeChecked()
    const householdsExport = householdsSection.getByRole('button', { name: 'Exporteren', exact: true })
    await expect(householdsExport).toBeVisible()
    await expect(householdsExport).toBeDisabled()
    const firstHouseholdCheckbox = householdsSection.getByRole('checkbox', { name: /Selecteer huishouden / }).first()
    await firstHouseholdCheckbox.check()
    await expect(householdsExport).toBeEnabled()

    const firstHouseholdRow = households.locator('tbody tr').first()
    await expect(firstHouseholdRow).toBeVisible()
    await firstHouseholdRow.dblclick()
    const inspector = page.getByTestId('superuser-household-inspector')
    await expect(inspector).toBeVisible()
    await expect(inspector.getByText(/Alleen lezen/i).first()).toBeVisible()
    await expect(inspector.getByText('Niet aan gebruiker herleidbaar', { exact: true })).toBeVisible()
    await expectSortableHeader(page.getByTestId('superuser-household-members-table'), 'Rol')
    await expectSortableHeader(page.getByTestId('superuser-household-members-table'), 'Status')
    await expect(inspector.getByLabel('Selecteer alle gebruikerscategorieën')).toBeChecked()

    await inspector.getByRole('tab', { name: 'Kassa', exact: true }).click()
    await expect(inspector.getByLabel("Technische ID's tonen")).not.toBeChecked()
    await expect(inspector.getByText(/Technische ID's:\s*Uit/i)).toBeVisible()
    await expect(inspector.getByText(/Voorkomens:\s*alleen actief/i)).toBeVisible()
    await expect(inspector.getByRole('navigation', { name: 'Paginering' }).last()).toBeVisible()
    await expect(inspector.getByRole('button', { name: 'Exporteren', exact: true })).toBeVisible()
    await expectReadOnlyInspector(inspector)
  })

  test('Gebruikers blijft binnen het frame met scrollbar, selectie, export en stabiele paginering', async ({ page }) => {
    await page.getByRole('tab', { name: 'Gebruikers', exact: true }).click()
    const section = page.getByTestId('superuser-users-section')
    await expect(section).toBeVisible()
    const table = page.getByTestId('superuser-users-table')
    await expect(table).toBeVisible()
    for (const header of ['Gebruiker', 'Huishouden', 'Rol', 'Status', 'Laatst actief', 'Toegevoegd op']) {
      await expectSortableHeader(table, header)
    }

    const pagination = section.getByRole('navigation', { name: 'Paginering' })
    await expect(pagination).toBeVisible()
    const centerBefore = await horizontalCenter(pagination)

    const technicalSelector = section.getByLabel("Technische ID's tonen in gebruikersoverzicht")
    await expect(technicalSelector).not.toBeChecked()
    await expect(table.getByRole('button', { name: 'Technisch gebruiker-ID sorteren', exact: true })).toHaveCount(0)
    await technicalSelector.check()
    await expectSortableHeader(table, 'Technisch gebruiker-ID')
    await expectSortableHeader(table, 'Technisch huishouden-ID')
    await expectHorizontalScrollbar(table)

    const centerWithTechnicalIds = await horizontalCenter(pagination)
    expect(Math.abs(centerWithTechnicalIds - centerBefore)).toBeLessThan(2)

    const firstResizeHandle = table.getByRole('separator', { name: 'Kolom breedte aanpassen' }).first()
    const resizeBox = await firstResizeHandle.boundingBox()
    if (!resizeBox) throw new Error('Kolombreedte-handle ontbreekt.')
    await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(resizeBox.x + resizeBox.width / 2 + 80, resizeBox.y + resizeBox.height / 2)
    await page.mouse.up()

    const centerAfterResize = await horizontalCenter(pagination)
    expect(Math.abs(centerAfterResize - centerWithTechnicalIds)).toBeLessThan(2)

    const exportButton = section.getByRole('button', { name: 'Exporteren', exact: true })
    await expect(exportButton).toBeVisible()
    await expect(exportButton).toBeDisabled()
    const firstUserCheckbox = section.getByRole('checkbox', { name: /Selecteer gebruiker / }).first()
    await firstUserCheckbox.check()
    await expect(exportButton).toBeEnabled()

    const controls = section.locator('.rz-data-table-controls')
    const controlsBox = await controls.boundingBox()
    const exportBox = await exportButton.boundingBox()
    if (!controlsBox || !exportBox) throw new Error('Paginering/export heeft geen bounding box.')
    expect(exportBox.x).toBeGreaterThan(controlsBox.x + controlsBox.width / 2)
    await expect(section.locator('textarea, form')).toHaveCount(0)
  })

  test('Gebruik is een operationele activiteitsanalyse en geen kopie van Overzicht', async ({ page }) => {
    await page.getByRole('tab', { name: 'Gebruik', exact: true }).click()
    const usageSection = page.getByTestId('superuser-usage')
    await expect(usageSection).toBeVisible()
    await expect(usageSection.getByText(/gebruiksvolume en activiteit/i)).toBeVisible()
    await expect(usageSection.getByText(/geen nieuwe gebruikers- of schermtracking toegevoegd/i)).toBeVisible()
    for (const label of ['Actieve gebruikers', 'Kassabonnen', 'Voorraadmutaties', 'Meldingen', 'Laatst actief']) {
      await expectSortableHeader(page.getByTestId('superuser-usage-table'), label)
    }
    const usageTable = usageSection.locator('[data-testid="superuser-usage-table"]')
    await expect(usageTable).toBeVisible()
    await expect(usageSection.getByRole('navigation', { name: 'Paginering' })).toBeVisible()
    await expect(usageSection.getByText(/Pagina 1 van/i)).toBeVisible()
    const firstUsageRow = usageTable.locator('tbody tr').first()
    if (await firstUsageRow.count()) {
      await firstUsageRow.dblclick()
      const inspector = page.getByTestId('superuser-household-inspector')
      await expect(inspector).toBeVisible()
      await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')
      await expect(inspector.getByText(/Alleen lezen/i).first()).toBeVisible()
    }
  })

  test('Aandacht vereist opent Meldingen voor het betreffende huishouden', async ({ page }) => {
    await page.route('**/api/superuser/overview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          metrics: { active_households: 1, active_users: 1, receipt_count: 0, open_notifications: 1 },
          notification_route: '/superuser/meldingen',
          attention_items: [{ household_id: '0', household_name: 'Regressietest huishouden 0', signal: '1 open melding', signal_count: 1 }],
        }),
      })
    })
    await page.reload()
    await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()
    const attentionRow = page.getByTestId('superuser-attention-table').locator('tbody tr').first()
    await expect(attentionRow).toBeVisible()
    await attentionRow.dblclick()
    await expect(page).toHaveURL(/\/superuser\/meldingen\?householdId=0$/)
    await expect(page.getByTestId('platform-support-page')).toBeVisible()
    await expect(page.getByLabel('Filter op huishouden')).toHaveValue('0')
    await expect(page.getByText(/Meldingen van en met huishouden 0/i)).toBeVisible()
  })

  test('Meldingen-tab springt direct naar de bestaande platformfunctionaliteit', async ({ page }) => {
    await page.getByRole('tab', { name: 'Meldingen', exact: true }).click()
    await expect(page).toHaveURL(/\/superuser\/meldingen$/)
    await expect(page.getByTestId('platform-support-page')).toBeVisible()
    await expect(page.getByText('Alle meldingen', { exact: true })).toBeVisible()
  })
})
