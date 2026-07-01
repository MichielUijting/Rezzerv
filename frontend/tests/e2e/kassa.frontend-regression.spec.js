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

    await expectNoConsoleErrors(consoleErrors);
  });

  test('Kassa nieuw-route blijft naar dezelfde flow leiden', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/kassa/nieuw', [
      'Kassa',
      'Kassabon',
      'Upload',
      'Inlezen',
    ]);

    await expect(page.locator('body')).toContainText(/Kassa|Kassabon|Upload|Inlezen/i);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Kassa toont parsekwaliteit diagnose', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.goto('/kassa');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByTestId('kassa-parse-quality-diagnostics')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Inleeskwaliteit' })).toBeVisible();

    await page.getByRole('button', { name: 'Inleeskwaliteit' }).click();
    await expect(page.getByText('Kassa parsekwaliteit diagnose')).toBeVisible();
    await expect(page.getByText('OFF zoektekst')).toBeVisible();
    await expect(page.getByText('Parserstatus')).toBeVisible();

    await expectNoConsoleErrors(consoleErrors);
  });
});
