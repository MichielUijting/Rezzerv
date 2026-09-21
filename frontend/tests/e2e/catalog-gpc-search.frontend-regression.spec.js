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

  test('toont automatisch maximaal vijf gerankte GPC-kandidaten zonder handmatige zoekactie', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'global-product-bouillon',
              name: 'AH Bouillon kip',
              brand: 'Albert Heijn',
              primary_gtin: '',
            },
          ],
          total: 1,
          limit: 2000,
          offset: 0,
        }),
      });
    });

    await page.route('**/api/catalog/global-product-bouillon/gpc-brick', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          assignment: null,
          suggestion: {
            brick_code: '10000001',
            brick_description: 'Bouillonblokjes',
            confidence: 0.91,
            confidence_label: 'hoog',
            match_strength_percent: 91,
            suggestion_reason: 'Overeenkomst met productgegevens: Bouillon',
          },
          suggestions: [
            {
              brick_code: '10000001',
              brick_description: 'Bouillonblokjes',
              class_description: 'Bouillon en fond',
              family_description: 'Soepen',
              segment_description: 'Voedingsmiddelen',
              confidence: 0.91,
              confidence_label: 'hoog',
              match_strength_percent: 91,
              suggestion_reason: 'Overeenkomst met productgegevens: Bouillon',
            },
            {
              brick_code: '10000002',
              brick_description: 'Bouillonpoeder',
              class_description: 'Bouillon en fond',
              family_description: 'Soepen',
              segment_description: 'Voedingsmiddelen',
              confidence: 0.78,
              confidence_label: 'hoog',
              match_strength_percent: 78,
              suggestion_reason: 'Overeenkomst met productgegevens: bouillon, soep',
            },
            {
              brick_code: '10000003',
              brick_description: 'Soepbasis',
              class_description: 'Soepbereidingen',
              family_description: 'Soepen',
              segment_description: 'Voedingsmiddelen',
              confidence: 0.63,
              confidence_label: 'redelijk',
              match_strength_percent: 63,
              suggestion_reason: 'Overeenkomst met productgegevens: soep',
            },
          ],
        }),
      });
    });

    await page.goto('/catalogus/gpc-classificeren');
    const articleSearch = page.getByPlaceholder('Zoeken op artikelnaam, merk, barcode, GTIN of EAN');
    await articleSearch.fill('Bouillon');
    await page.getByRole('button', { name: /AH Bouillon kip/ }).click();

    await expect(page.getByTestId('catalog-gpc-action-suggestions')).toBeVisible();
    await expect(page.getByTestId('catalog-gpc-action-suggestion')).toHaveCount(3);
    await expect(page.getByText('Waarschijnlijke GPC Bricks')).toBeVisible();
    await expect(page.getByText(/Matchsterkte: 91%/)).toBeVisible();
    await expect(page.getByText(/10000001 — Bouillonblokjes/)).toBeVisible();
    await expect(page.getByText(/10000002 — Bouillonpoeder/)).toBeVisible();
    await expect(page.getByText(/10000003 — Soepbasis/)).toBeVisible();

    await expect(page.getByPlaceholder('Zoeken op Brickcode of Nederlandse/Engelse Brickomschrijving')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('Catalogustabel houdt titel en zoekfilters sticky en begrenst de pagina op tien inhoudelijke rijen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let requestedLimit = null;

    await page.route('**/api/catalog?*', async (route) => {
      const url = new URL(route.request().url());
      requestedLimit = url.searchParams.get('limit');
      const items = Array.from({ length: 10 }, (_, index) => ({
        id: `catalog-row-${index + 1}`,
        name: `Catalogusartikel ${index + 1}`,
        catalog_kind: index % 2 ? 'generic' : 'exact',
        brand: index % 2 ? '' : 'Merk',
        primary_gtin: `87100000000${String(index).padStart(2, '0')}`,
        product_type: 'Test Producttype',
        household_article_count: index,
        image_url: '',
      }));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items, total: 10, limit: 10, offset: 0 }),
      });
    });

    await page.goto('/catalogus');
    const table = page.getByTestId('catalog-table');
    await expect(table).toBeVisible();
    await expect(table.locator('tbody tr')).toHaveCount(10);
    expect(requestedLimit).toBe('10');

    const wrapper = table.locator('..');
    await wrapper.evaluate((node) => {
      node.style.maxHeight = '180px';
      node.scrollTop = 160;
    });
    await page.waitForTimeout(50);

    const wrapperBox = await wrapper.boundingBox();
    const headerBox = await table.locator('thead tr.rz-table-header th').first().boundingBox();
    const filterBox = await table.locator('thead tr.rz-table-filters th').first().boundingBox();

    expect(wrapperBox).not.toBeNull();
    expect(headerBox).not.toBeNull();
    expect(filterBox).not.toBeNull();
    expect(Math.abs(headerBox.y - wrapperBox.y)).toBeLessThanOrEqual(3);
    expect(Math.abs(filterBox.y - (headerBox.y + headerBox.height))).toBeLessThanOrEqual(3);
    await expectNoConsoleErrors(consoleErrors);
  });


  test('alleen superuser kan geselecteerde Catalogusartikelen verwijderen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let catalogItems = [
      {
        id: 'catalog-delete-me',
        name: 'Verwijder mij',
        catalog_kind: 'exact',
        brand: 'Testmerk',
        primary_gtin: '8711111111111',
        product_type: 'Testtype',
        household_article_count: 0,
        image_url: '',
      },
      {
        id: 'catalog-keep-me',
        name: 'Bewaar mij',
        catalog_kind: 'exact',
        brand: 'Testmerk',
        primary_gtin: '8722222222222',
        product_type: 'Testtype',
        household_article_count: 0,
        image_url: '',
      },
    ];
    let deletePayload = null;

    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'platform-superuser',
          email: 'supergebruiker@rezzerv.local',
          active_household_id: '0',
          context_type: 'system',
          role: 'owner',
          display_role: 'admin',
          is_platform_superuser: true,
          permissions: {
            'platform.system_household.access': true,
            'gpc.update': true,
          },
        }),
      });
    });

    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: catalogItems,
          total: catalogItems.length,
          limit: 10,
          offset: 0,
        }),
      });
    });

    await page.route('**/api/catalog/bulk-delete', async (route) => {
      deletePayload = JSON.parse(route.request().postData() || '{}');
      const ids = Array.isArray(deletePayload.global_product_ids) ? deletePayload.global_product_ids : [];
      catalogItems = catalogItems.filter((item) => !ids.includes(item.id));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          deleted_count: ids.length,
          deleted_ids: ids,
          already_deleted_ids: [],
          not_found_ids: [],
        }),
      });
    });

    await page.goto('/catalogus');
    await expect(page.getByTestId('catalog-bulk-delete')).toBeVisible();
    await expect(page.getByTestId('catalog-bulk-delete')).toBeDisabled();

    await page.getByLabel('Selecteer Verwijder mij').check();
    await expect(page.getByTestId('catalog-bulk-delete')).toBeEnabled();
    await page.getByTestId('catalog-bulk-delete').click();

    const confirmation = page.getByTestId('catalog-bulk-delete-confirmation');
    await expect(confirmation).toBeVisible();
    await expect(confirmation.getByText('1 geselecteerd catalogusartikel verwijderen?', { exact: true })).toBeVisible();
    await page.getByTestId('catalog-bulk-delete-confirmation-primary-button').click();

    await expect.poll(() => deletePayload).toEqual({ global_product_ids: ['catalog-delete-me'] });
    await expect(page.getByTestId('catalog-row-catalog-delete-me')).toHaveCount(0);
    await expect(page.getByTestId('catalog-row-catalog-keep-me')).toBeVisible();
    await expect(page.getByText('1 catalogusartikel verwijderd.', { exact: true })).toBeVisible();
    await expectNoConsoleErrors(consoleErrors);
  });


  test('IP-owner met systeemtoegang krijgt geen superuser Catalogus-verwijderactie', async ({ page }) => {
    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'platform-ip-owner',
          email: 'ip-owner@example.test',
          active_household_id: '0',
          context_type: 'system',
          role: 'owner',
          display_role: 'admin',
          is_platform_superuser: false,
          is_ip_owner: true,
          permissions: {
            'platform.system_household.access': true,
            'platform.catalog.manage': true,
          },
        }),
      });
    });
    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'catalog-ip-owner-visible',
            name: 'IP-owner zichtbaar artikel',
            catalog_kind: 'exact',
            brand: '',
            primary_gtin: '8744444444444',
            product_type: '',
            household_article_count: 0,
            image_url: '',
          }],
          total: 1,
          limit: 10,
          offset: 0,
        }),
      });
    });

    await page.goto('/catalogus');
    await expect(page.getByTestId('catalog-row-catalog-ip-owner-visible')).toBeVisible();
    await expect(page.getByTestId('catalog-bulk-delete')).toHaveCount(0);
  });


  test('normale gebruiker krijgt geen Catalogus-verwijderactie', async ({ page }) => {
    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'regular-user',
          email: 'gebruiker@example.test',
          active_household_id: 'household-1',
          context_type: 'regular',
          role: 'member',
          display_role: 'lid',
          is_platform_superuser: false,
          permissions: {},
        }),
      });
    });
    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'catalog-visible',
            name: 'Zichtbaar artikel',
            catalog_kind: 'exact',
            brand: '',
            primary_gtin: '8733333333333',
            product_type: '',
            household_article_count: 0,
            image_url: '',
          }],
          total: 1,
          limit: 10,
          offset: 0,
        }),
      });
    });

    await page.goto('/catalogus');
    await expect(page.getByTestId('catalog-row-catalog-visible')).toBeVisible();
    await expect(page.getByTestId('catalog-bulk-delete')).toHaveCount(0);
  });


  test('langdurig zoeken naar GPC Bricks toont pas na één seconde het grote Inhuis-logo', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let releaseBrickSearch;
    let markBrickSearchStarted;
    const brickSearchGate = new Promise((resolve) => { releaseBrickSearch = resolve; });
    const brickSearchStarted = new Promise((resolve) => { markBrickSearchStarted = resolve; });

    await page.route('**/api/catalog?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'global-product-overlay-test',
            name: 'Langzame Brick zoektest',
            brand: 'Inhuis',
            primary_gtin: '8710000000999',
          }],
          total: 1,
          limit: 2000,
          offset: 0,
        }),
      });
    });

    await page.route('**/api/catalog/global-product-overlay-test/gpc-brick', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ assignment: null, suggestions: [] }),
      });
    });

    await page.route('**/api/catalog/gpc/bricks?*', async (route) => {
      markBrickSearchStarted();
      await brickSearchGate;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            brick_code: '10000167',
            brick_description: 'Kaas — Smeerbaar',
            segment_description: 'Voedingsmiddelen',
            family_description: 'Zuivel',
            class_description: 'Kaas',
          }],
        }),
      });
    });

    await page.goto('/catalogus/gpc-classificeren');
    await page.getByPlaceholder('Zoeken op artikelnaam, merk, barcode, GTIN of EAN').fill('Langzame');
    await page.getByRole('button', { name: /Langzame Brick zoektest/ }).click();

    const brickSearch = page.getByPlaceholder('Zoeken op Brickcode of Nederlandse/Engelse Brickomschrijving');
    await expect(brickSearch).toBeVisible();
    await brickSearch.fill('kaas');
    await brickSearchStarted;

    const overlay = page.getByRole('status', { name: 'Gegevens worden geladen' });
    await expect(overlay).toHaveCount(0);
    await page.waitForTimeout(850);
    await expect(overlay).toHaveCount(0);
    await page.waitForTimeout(300);
    await expect(overlay).toBeVisible();
    await expect(page.getByTestId('table-loading-logo')).toHaveAttribute('src', '/inhuis-loading-mark.svg');
    await expect(page.getByTestId('table-loading-logo')).toHaveCSS('width', '420px');

    releaseBrickSearch();

    await expect(page.getByRole('button', { name: /10000167 — Kaas — Smeerbaar/ })).toBeVisible();
    await expect(overlay).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });

});
