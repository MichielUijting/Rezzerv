import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions.js';

test.describe('Kassa frontend-regressie', () => {
  test('Kassa hoofdscherm laadt zonder frontendcorruptie', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/kassa', [
      'Kassa',
      'Kassabon',
      'Bon',
      'Upload',
      'Inlezen',
    ]);

    await expectAnyVisible(page, [
      'Kassa',
      'Kassabon',
      'Upload',
      'Voorbewerkt',
      'Bonregels',
      'Status',
    ], 'Kassa kernlabels');

    await expect(page.getByRole('button', { name: 'Inleeskwaliteit' })).toHaveCount(0);
    await expect(page.getByTestId('kassa-parse-quality-diagnostics')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Kassa nieuw-route blijft naar dezelfde flow leiden', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/kassa/nieuw', [
      'Bon toevoegen',
      'Sleep hier je kassabon',
      'Bestanden kiezen',
      'Camera openen',
    ]);

    await expect(page.locator('body')).toContainText(/Bon toevoegen|Sleep hier je kassabon|Bestanden kiezen|Camera openen/i);
    await expect(page.getByRole('button', { name: 'Inleeskwaliteit' })).toHaveCount(0);
    await expect(page.getByTestId('kassa-parse-quality-diagnostics')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
