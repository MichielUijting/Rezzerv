import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Externe databases frontend-regressie', () => {
  test('Externe databases scherm laadt en behoudt bonartikelen-overzicht', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/externe-databases', [
      'Externe databases',
      'Open Food Facts',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ]);

    await expectAnyVisible(page, [
      'Externe databases',
      'Open Food Facts',
      'Bonartikelen',
      'Kandidaten',
      'Product',
    ], 'Externe databases kernlabels');

    await page.getByRole('button', { name: 'Test kandidaat' }).click();

    await expect(page.getByTestId('external-database-preview-meta')).toBeVisible();
    await expect(page.getByText('Bron:', { exact: false })).toBeVisible();
    await expect(page.getByText('lidl_taxonomy', { exact: false })).toBeVisible();
    await expect(page.getByTestId('external-database-off-query-terms')).toBeVisible();
    await expect(page.getByTestId('external-database-off-query-terms')).toContainText('kania taco specerijenmix');
    await expectAnyVisible(page, [
      'Kania Taco Specerijenmix',
      'Kania Burrito Specerijenmix',
      'Kania Fajita Specerijenmix',
    ], 'Lidl kandidaatpreview');

    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
