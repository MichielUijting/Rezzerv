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

test('Superuser KPI-trendkaarten tonen rechts het 7-daagse groeipercentage', async ({ page }) => {
  await loginAsSuperuser(page)
  await page.goto('/superuser')
  await expect(page.getByTestId('superuser-platform-overview')).toBeVisible()

  for (const testId of [
    'superuser-metric-active-households',
    'superuser-metric-active-users',
    'superuser-metric-receipts',
    'superuser-metric-open-notifications',
  ]) {
    const metric = page.getByTestId(testId)
    const growth = page.getByTestId(`${testId}-growth`)
    await expect(metric).toHaveAttribute('data-trend-points', '7')
    await expect(growth).toBeVisible()
    await expect(growth).toHaveAttribute('aria-label', /groei afgelopen 7 kalenderdagen/i)
    await expect(growth).toHaveText(/^(?:[+−]\d+(?:,\d)?%|0%|—)$/)

    const metricBox = await metric.boundingBox()
    const growthBox = await growth.boundingBox()
    if (!metricBox || !growthBox) throw new Error('KPI-kaart of groeipercentage heeft geen bounding box.')
    expect(growthBox.x + growthBox.width / 2).toBeGreaterThan(metricBox.x + metricBox.width / 2)
  }
})
