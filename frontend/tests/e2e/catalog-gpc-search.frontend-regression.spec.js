import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

test.describe('Catalogus GPC Brick zoekfunctie frontend-regressie', () => {
  test('zoekt Producttype op Nederlandse Brickomschrijving en Brickcode', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const searchQueries = [];

    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'global-product-boursin',
              name: 'Boursin Knoflook & Fijne Kruiden',
              brand: 'Boursin',
              primary_gtin: '3073780966000',
            },
          ],
          total: 1,
          limit: 2000,
          offset: 0,
        }),
      });
    });

    await page.route('**/api/catalog/global-product-boursin/gpc-brick', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ assignment: null, suggestion: null }),
      });
    });

    await page.route('**/api/catalog/gpc/bricks?*', async (route) => {
      const url = new URL(route.request().url());
      const query = url.searchParams.get('query') || '';
      searchQueries.push(query);
      const normalized = query.toLowerCase();
      const matches = normalized.includes('kaas') || normalized.includes('10000167');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: matches
            ? [
                {
                  brick_code: '10000167',
                  brick_description: 'Kaas — Smeerbaar',
                  brick_description_en: 'Cheese — Spreadable',
                  class_code: '50131700',
                  class_description: 'Kaas en kaassubstituten',
                  family_code: '50130000',
                  family_description: 'Melk, boter, room, yoghurt, kaas, eieren en substituten',
                  segment_code: '50000000',
                  segment_description: 'Voedingsmiddelen, dranken en tabak',
                },
              ]
            : [],
        }),
      });
    });

    await page.goto('/catalogus/gpc-classificeren');
    await expect(page.getByTestId('catalog-gpc-action-page')).toBeVisible();

    const articleSearch = page.getByPlaceholder('Zoeken op artikelnaam, merk, barcode, GTIN of EAN');
    await articleSearch.fill('Boursin');
    await page.getByRole('button', { name: /3073780966000 — Boursin Knoflook/ }).click();

    const brickSearch = page.getByPlaceholder('Zoeken op Brickcode of Nederlandse/Engelse Brickomschrijving');
    await expect(brickSearch).toBeVisible();

    await brickSearch.fill('kaas');
    await expect(page.getByRole('button', { name: /10000167 — Kaas — Smeerbaar/ })).toBeVisible();
    await expect.poll(() => searchQueries).toContain('kaas');

    await brickSearch.fill('10000167');
    await expect(page.getByRole('button', { name: /10000167 — Kaas — Smeerbaar/ })).toBeVisible();
    await expect.poll(() => searchQueries).toContain('10000167');

    await expect(page.getByText('Geen passende GPC Bricks gevonden.')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });
});
