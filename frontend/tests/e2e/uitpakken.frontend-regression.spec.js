import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions';
import { apiFetch, resolveAuthorizedHouseholdId } from './helpers/devApi';

test.describe('Uitpakken frontend-regressie', () => {
  test('Kassabonnen overzicht laadt zonder frontendcorruptie', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/kassabonnen', [
      'Kassabonnen',
      'Kassa',
      'Bon',
      'Winkel',
      'Status',
    ]);

    await expectNoConsoleErrors(consoleErrors);
  });

  test('Open batch detail blijft bereikbaar voor uitpakken-flow', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    const householdId = await resolveAuthorizedHouseholdId(page.request);
    const connections = await apiFetch(
      page.request,
      `/api/store-connections?householdId=${encodeURIComponent(householdId)}`
    );

    const activeConnection = connections.find((item) => item.store_provider_code === 'lidl') || connections[0];
    if (!activeConnection) {
      throw new Error('Geen actieve winkelkoppeling beschikbaar voor uitpakken-regressie.');
    }

    const latestBatch = await apiFetch(
      page.request,
      `/api/store-connections/${activeConnection.id}/latest-batch`
    );

    const batchId =
      latestBatch?.batch_id ||
      latestBatch?.id ||
      latestBatch?.batch?.id ||
      latestBatch?.purchase_import_batch_id;

    if (!batchId) {
      throw new Error(`Geen batch-id gevonden in latest-batch response: ${JSON.stringify(latestBatch)}`);
    }

    await page.goto(`/kassabonnen/batch/${batchId}`);
    await expect(page).toHaveURL(/\/kassabonnen\/batch\//);

    await expect(page.locator('body')).toBeVisible();
    await expectAnyVisible(page, [
      'Kassabon',
      'Artikel',
      'Locatie',
      'Sublocatie',
      'Verwerken',
      'Uitpakken',
    ], 'uitpakken detail');

    await expectNoConsoleErrors(consoleErrors);
  });

  test('Locatiebeheer blijft als route beschikbaar voor uitpakken-flow', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await expectRouteLoads(page, '/instellingen/locaties', [
      'Beheer locaties',
      'Locaties',
      'Sublocaties',
      'Actief',
    ]);

    await expectNoConsoleErrors(consoleErrors);
  });
});
