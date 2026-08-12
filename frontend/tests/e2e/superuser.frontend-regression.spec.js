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

  test('beheercentrum bewaakt tabs, uitgebreid huishoudsoverzicht en read-only huishoudinzage', async ({ page }) => {
    await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')
    for (const tabName of ['Overzicht', 'Huishoudens', 'Gebruikers', 'Gebruik', 'Kassabonnen', 'Meldingen', 'Systeem']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible()
    }

    await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()
    for (const label of ['Actieve huishoudens', 'Actieve gebruikers', 'Kassabonnen', 'Open meldingen', 'Aandacht vereist']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }

    await page.getByRole('tab', { name: 'Huishoudens', exact: true }).click()
    const households = page.getByTestId('superuser-households-table')
    await expect(households).toBeVisible()
    for (const header of ['Huishouden', 'Status', 'Actieve gebruikers', 'Gearchiveerd', 'Aangemaakt op', 'Laatst actief', 'Kassabonnen', 'Open meldingen', 'Aandacht vereist']) {
      await expect(households.getByRole('columnheader', { name: header, exact: true })).toBeVisible()
    }
    await expect(page.getByRole('navigation', { name: 'Paginering' })).toBeVisible()

    const firstHouseholdRow = households.locator('tbody tr').first()
    await expect(firstHouseholdRow).toBeVisible()
    await firstHouseholdRow.dblclick()
    const inspector = page.getByTestId('superuser-household-inspector')
    await expect(inspector).toBeVisible()
    await expect(inspector.getByText(/Alleen lezen/i).first()).toBeVisible()
    await expect(inspector.getByText('Niet aan gebruiker herleidbaar', { exact: true })).toBeVisible()
    await expect(inspector.getByRole('columnheader', { name: 'Rol' })).toBeVisible()
    await expect(inspector.getByRole('columnheader', { name: 'Status' })).toBeVisible()
    await expect(inspector.getByLabel('Selecteer alle gebruikerscategorieën')).toBeChecked()

    await inspector.getByRole('tab', { name: 'Kassa', exact: true }).click()
    await expect(inspector.getByLabel("Technische ID's tonen")).not.toBeChecked()
    await expect(inspector.getByText(/Technische ID's:\s*Uit/i)).toBeVisible()
    await expect(inspector.getByText(/Voorkomens:\s*alleen actief/i)).toBeVisible()
    await expect(inspector.getByRole('navigation', { name: 'Paginering' }).last()).toBeVisible()
    await expect(inspector.getByRole('button', { name: 'Exporteren', exact: true })).toBeVisible()
    await expectReadOnlyInspector(inspector)
  })

  test('Gebruikers toont platformbrede read-only huishoudkoppelingen met technische ID selector', async ({ page }) => {
    await page.getByRole('tab', { name: 'Gebruikers', exact: true }).click()
    const section = page.getByTestId('superuser-users-section')
    await expect(section).toBeVisible()
    const table = page.getByTestId('superuser-users-table')
    await expect(table).toBeVisible()
    for (const header of ['Gebruiker', 'Huishouden', 'Rol', 'Status', 'Laatst actief', 'Toegevoegd op']) {
      await expect(table.getByRole('columnheader', { name: header, exact: true })).toBeVisible()
    }
    const technicalSelector = section.getByLabel("Technische ID's tonen in gebruikersoverzicht")
    await expect(technicalSelector).not.toBeChecked()
    await expect(table.getByRole('columnheader', { name: 'Technisch gebruiker-ID', exact: true })).toHaveCount(0)
    await technicalSelector.check()
    await expect(table.getByRole('columnheader', { name: 'Technisch gebruiker-ID', exact: true })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Technisch huishouden-ID', exact: true })).toBeVisible()
    await expect(section.getByRole('navigation', { name: 'Paginering' })).toBeVisible()
    await expect(section.locator('textarea, form')).toHaveCount(0)
  })

  test('Gebruik blijft een read-only platformprojectie met standaardtabel en doorklik', async ({ page }) => {
    await page.getByRole('tab', { name: 'Gebruik', exact: true }).click()
    const usageSection = page.getByTestId('superuser-usage')
    await expect(usageSection).toBeVisible()
    await expect(usageSection.getByText(/geen nieuwe gebruikers- of schermtracking toegevoegd/i)).toBeVisible()
    for (const label of ['Actieve gebruikers', 'Kassabonnen', 'Voorraadmutaties', 'Meldingen', 'Laatst actief']) {
      await expect(usageSection.getByRole('columnheader', { name: label })).toBeVisible()
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

  test('Meldingen is als vaste Superuser-tab beschikbaar en gebruikt bestaande platformroute', async ({ page }) => {
    await page.getByRole('tab', { name: 'Meldingen', exact: true }).click()
    const section = page.getByTestId('superuser-notifications-tab')
    await expect(section).toBeVisible()
    await section.getByRole('button', { name: 'Naar Meldingen', exact: true }).click()
    await expect(page).toHaveURL(/\/superuser\/meldingen$/)
    await expect(page.getByTestId('platform-support-page')).toBeVisible()
  })
})
