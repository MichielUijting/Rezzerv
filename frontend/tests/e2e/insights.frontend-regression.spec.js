import { test, expect } from '@playwright/test'

test('Inzichten is vanaf Startpagina bereikbaar en toont benchmarkperspectieven', async ({ page }) => {
  await page.goto('/home')
  await expect(page.getByText('Startpagina')).toBeVisible()

  await page.getByText('Inzichten', { exact: true }).click()
  await expect(page).toHaveURL(/\/inzichten$/)
  await expect(page.getByTestId('insights-page')).toBeVisible()
  await expect(page.getByText('Prototype · voorbeelddata')).toBeVisible()

  await expect(page.getByRole('tab', { name: 'Overzicht' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('Dit valt op')).toBeVisible()
  await expect(page.getByText('Jij versus vergelijkbare huishoudens')).toBeVisible()

  await page.getByRole('tab', { name: 'Benchmark' }).click()
  await expect(page.getByRole('button', { name: 'Vergelijkbaar huishouden' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Postcodegebied' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Leeftijdscategorie' })).toBeVisible()

  await page.getByRole('button', { name: 'Postcodegebied' }).click()
  await expect(page.getByText('voldoende grote, geanonimiseerde regiogroep')).toBeVisible()
  await expect(page.getByText('Privacygrens voor benchmarks')).toBeVisible()
})
