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

    await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
