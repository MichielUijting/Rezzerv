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

    await expect(page.getByText('Lidl-kandidaatpreview')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Test kandidaat' })).toHaveCount(0);

    const receiptTable = page.getByTestId('external-receipt-items-table');
    await expect(receiptTable).toBeVisible();

    const firstDataRow = receiptTable.locator('tbody tr').filter({ hasText: /[A-Za-z0-9]/ }).first();
    await firstDataRow.dblclick();

    await expect(page.getByText('Koppelen kandidaten in artikel-catalogus')).toBeVisible();
    await expect(page.getByTestId('external-receipt-item-candidates-table')).toBeVisible();

    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
