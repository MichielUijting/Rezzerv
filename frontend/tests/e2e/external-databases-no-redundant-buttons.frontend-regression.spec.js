import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases navigatieknoppen regressie', () => {
  test('Terug en Vernieuwen zijn niet aanwezig op Externe databases', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/external-databases/receipt-items?limit=500', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
    });

    await page.goto('/externe-databases');
    await expect(page.getByTestId('external-databases-page')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Terug' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Vernieuwen' })).toHaveCount(0);
    await expect(page.getByText('Bonartikelen worden geladen...')).toHaveCount(0);
    await expect(page.getByText('Externe databases worden geladen...')).toHaveCount(0);

    await expectNoConsoleErrors(consoleErrors);
  });
});
