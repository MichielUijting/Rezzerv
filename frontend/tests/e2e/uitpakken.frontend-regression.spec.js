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

  test('Universele artikelnaam blijft in Uitpakken gekoppeld en bontekst blijft alleen bontekst', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const batchId = 'universal-name-regression';
    const lineId = 'line-universal-mosterd';
    const universalArticleName = 'Mosterd fijne Dijon extra lange universele artikelnaam';
    const receiptArticleText = 'MOSTERD DIJON 250G';

    await page.route('**/api/household', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '1',
          is_viewer: false,
          permissions: { 'article.create': true },
          store_import_simplification_level: 'gebalanceerd',
        }),
      });
    });

    await page.route('**/api/store-providers', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ code: 'lidl', name: 'Lidl' }]),
      });
    });

    await page.route('**/api/store-review-articles', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'household-article-mosterd',
            name: universalArticleName,
            article_name: universalArticleName,
            label: universalArticleName,
          },
        ]),
      });
    });

    await page.route('**/api/spaces*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      });
    });

    await page.route('**/api/sublocations*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      });
    });

    await page.route(`**/api/purchase-import-batches/${batchId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          batch_id: batchId,
          store_provider_code: 'lidl',
          store_label: 'Lidl',
          purchase_date: '2026-07-17',
          import_status: 'review',
          lines: [
            {
              id: lineId,
              article_name_raw: receiptArticleText,
              quantity_raw: 1,
              unit_raw: 'stuk',
              matched_household_article_id: 'household-article-mosterd',
              suggested_household_article_id: 'household-article-mosterd',
              resolved_household_article_name: universalArticleName,
              target_location_id: '',
              processing_status: 'pending',
              review_decision: 'pending',
              match_status: 'matched',
            },
          ],
        }),
      });
    });

    await page.goto(`/kassabonnen/batch/${batchId}`);

    await expect(page).toHaveURL(new RegExp(`/kassabonnen/batch/${batchId}$`));
    const row = page.getByTestId(`receipt-line-${lineId}`);
    await expect(row).toBeVisible();

    const linkedArticleCell = page.getByTestId(`receipt-line-article-select-${lineId}`);
    await expect(linkedArticleCell).toContainText(universalArticleName);
    await expect(linkedArticleCell).not.toContainText(receiptArticleText);

    const bonArticleCell = row.locator('.rz-store-batch-col-item');
    await expect(bonArticleCell).toContainText('Mosterd Dijon 250g');
    await expect(bonArticleCell).not.toContainText(universalArticleName);

    await expectNoConsoleErrors(consoleErrors);
  });

});
