import { test, expect } from '@playwright/test'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://frontend:5174'

test.describe('Artikelgroep terminologie', () => {
  test('frontend bundle toont geen Mijn artikel meer in Uitpakken-relevante routes', async ({ page }) => {
    const seen = []

    page.on('response', async (response) => {
      const url = response.url()
      if (!url.includes('/assets/') || !url.endsWith('.js')) return
      try {
        const body = await response.text()
        if (body.includes('Mijn artikel') || body.includes('mijn artikel')) {
          seen.push(url)
        }
      } catch {
        // Ignore unreadable browser assets; visible UI assertion below remains leading.
      }
    })

    await page.goto(`${BASE_URL}/kassabonnen`, { waitUntil: 'networkidle' })

    await expect(page.locator('body')).not.toContainText('Mijn artikel')
    await expect(page.locator('body')).not.toContainText('mijn artikel')
    expect(seen).toEqual([])
  })
})
