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

test.describe('Superuser frontend-regressie', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsSuperuser(page)
    await page.goto('/superuser')
    await expect(page.getByTestId('superuser-dashboard')).toBeVisible()
  })

  test('beheercentrum bewaakt tabs, overzicht en read-only huishoudinzage', async ({ page }) => {
    await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')

    for (const tabName of ['Overzicht', 'Huishoudens', 'Gebruik', 'Kassabonnen', 'Systeem']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible()
    }

    await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()
    for (const label of ['Actieve huishoudens', 'Actieve gebruikers', 'Kassabonnen', 'Open meldingen', 'Aandacht vereist']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
    }

    await page.getByRole('tab', { name: 'Huishoudens', exact: true }).click()
    const households = page.getByTestId('superuser-households-table')
    await expect(households).toBeVisible()

    const firstHouseholdRow = households.locator('tbody tr').first()
    await expect(firstHouseholdRow).toBeVisible()
    await firstHouseholdRow.dblclick()

    await expect(page.getByTestId('superuser-household-inspector')).toBeVisible()
    await expect(page.getByText('Niet aan gebruiker herleidbaar', { exact: true })).toBeVisible()

    const inspector = page.getByTestId('superuser-household-inspector')
    await expect(inspector.getByRole('columnheader', { name: 'Rol' })).toBeVisible()
    await expect(inspector.getByRole('columnheader', { name: 'Status' })).toBeVisible()

    // Technische-ID-weergave hoort bij de detailtabellen, niet bij de standaardtab Diagnose.
    await inspector.getByRole('tab', { name: 'Kassa', exact: true }).click()
    await expect(inspector.getByLabel("Technische ID's tonen")).not.toBeChecked()
    await expect(inspector.getByText(/Voorkomens:\s*alleen actief/i)).toBeVisible()

    const mutationInputs = inspector.locator('input:not([type="checkbox"]), textarea')
    await expect(mutationInputs).toHaveCount(0)
  })

  test('Gebruik blijft een read-only platformprojectie met standaardtabel en doorklik', async ({ page }) => {
    await page.getByRole('tab', { name: 'Gebruik', exact: true }).click()

    await expect(page.getByText(/geen nieuwe gebruikers- of schermtracking toegevoegd/i)).toBeVisible()
    for (const label of ['Actieve gebruikers', 'Kassabonnen', 'Voorraadmutaties', 'Meldingen', 'Laatst actief']) {
      await expect(page.getByRole('columnheader', { name: label })).toBeVisible()
    }

    const usageTable = page.locator('[data-testid="superuser-usage-table"]')
    await expect(usageTable).toBeVisible()

    // De standaard Pagination is een sibling-control van DataTable en niet onderdeel van het <table>-element.
    const usageSection = page.getByTestId('superuser-usage')
    await expect(usageSection.getByRole('navigation', { name: 'Paginering' })).toBeVisible()
    await expect(usageSection.getByText(/Pagina 1 van/i)).toBeVisible()

    const firstUsageRow = usageTable.locator('tbody tr').first()
    if (await firstUsageRow.count()) {
      await firstUsageRow.dblclick()
      await expect(page.getByTestId('superuser-household-inspector')).toBeVisible()
      await expect(page.getByRole('status', { name: 'Superuser alleen-lezen status' })).toContainText('alleen lezen')
    }
  })
})
