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

  test('Oude losse kassabonroute verwijst naar volledig Uitpakken', async ({ page }) => {
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
    await expect(page).toHaveURL(new RegExp(`/kassabonnen\\?batch=${batchId}$`));

    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('Kassabon Kassabon')).toHaveCount(0);
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

  test('Oude bonartikeldetailroute verwijst naar volledig Uitpakken', async ({ page }) => {
    await page.goto('/kassabonnen/batch/legacy-batch/regel/legacy-line');
    await expect(page).toHaveURL(/\/kassabonnen\?batch=legacy-batch$/);
    await expect(page.getByText('Kassabon Kassabon')).toHaveCount(0);
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

    await page.route('**/api/unpack-start-batches*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            batch_id: batchId,
            store_provider_code: 'lidl',
            store_label: 'Lidl',
            purchase_date: '2026-07-17',
            inbox_status: 'Gecontroleerd',
            summary: { total: 1 },
          }],
        }),
      });
    });

    await page.route(`**/api/purchase-import-batches/${batchId}*`, async (route) => {
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
              matched_global_product_name: universalArticleName,
              target_location_id: '',
              processing_status: 'pending',
              review_decision: 'pending',
              match_status: 'matched',
            },
          ],
        }),
      });
    });

    await page.goto(`/kassabonnen?batch=${batchId}`);

    await expect(page).toHaveURL(new RegExp(`/kassabonnen\\?batch=${batchId}$`));
    const row = page.getByTestId(`receipt-line-${lineId}`);
    await expect(row).toBeVisible();

    await page.getByTestId(`receipt-line-${lineId}`).locator('td').nth(1).dblclick();
    await expect(page).toHaveURL(new RegExp(`/kassabonnen\\?batch=${batchId}$`));
    await expect(page.getByTestId('receipt-line-detail-overlay')).toBeVisible();
    const linkedArticleCell = page.getByTestId(`receipt-line-article-select-${lineId}`);
    await expect(linkedArticleCell).toContainText(universalArticleName);
    await expect(linkedArticleCell).not.toContainText(receiptArticleText);

    const universalProductField = page.getByTestId(`receipt-line-standard-product-${lineId}`);
    await expect(universalProductField).toBeVisible();
    await expect(universalProductField).toHaveValue(universalArticleName);

    const scanButtonBox = await page.getByTestId(`receipt-line-barcode-scan-${lineId}`).boundingBox();
    const checkButtonBox = await page.getByTestId(`receipt-line-barcode-check-${lineId}`).boundingBox();
    expect(scanButtonBox?.height).toBe(checkButtonBox?.height);

    await page.getByRole('button', { name: 'Sluit bonartikeldetails' }).click();
    await expect(page).toHaveURL(new RegExp(`/kassabonnen\\?batch=${batchId}$`));
    await expect(page.getByTestId('receipt-line-detail-overlay')).toHaveCount(0);
    await expect(page.getByTestId('receipts-table')).toBeVisible();
    const refreshedRow = page.getByTestId(`receipt-line-${lineId}`);
    const bonArticleCell = refreshedRow.locator('.rz-store-batch-col-item');
    await expect(bonArticleCell).toContainText('Mosterd Dijon 250g');
    await expect(bonArticleCell).not.toContainText(universalArticleName);
    const articleSelect = refreshedRow.locator('td').nth(4).locator('select');
    await expect(articleSelect).toHaveValue('household-article-mosterd');
    await expect(articleSelect.locator('option:checked')).toHaveText(universalArticleName);

    await expectNoConsoleErrors(consoleErrors);
  });

  test('Geldige GTIN wordt na bevestiging centraal opgeslagen en lokaal gekoppeld', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const batchId = 'barcode-save-regression';
    const lineId = 'line-barcode-mosterd';
    const gtin = '8712345678906';
    const householdArticleId = 'household-article-mosterd';
    const mutationRequests = [];
    let saved = false;

    page.on('request', (request) => {
      const url = request.url();
      if (
        /inventory|purchase|external-product-links|household-articles|save-household-article/.test(url)
        && request.method() !== 'GET'
      ) {
        mutationRequests.push(`${request.method()} ${url}`);
      }
    });

    await page.route('**/api/household', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '1',
        is_viewer: false,
        permissions: { 'article.create': true },
        store_import_simplification_level: 'gebalanceerd',
      }),
    }));

    await page.route('**/api/store-providers', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ code: 'lidl', name: 'Lidl' }]),
    }));

    await page.route('**/api/store-review-articles', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        id: householdArticleId,
        naam: 'Mosterd',
        custom_name: 'Mosterd',
      }]),
    }));

    await page.route('**/api/spaces*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }));

    await page.route('**/api/sublocations*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }));

    await page.route('**/api/unpack-start-batches*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [{
          batch_id: batchId,
          store_provider_code: 'lidl',
          store_label: 'Lidl',
          purchase_date: '2026-07-25',
          inbox_status: 'Gecontroleerd',
          summary: { total: 1 },
        }],
      }),
    }));

    await page.route(`**/api/purchase-import-batches/${batchId}*`, async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        batch_id: batchId,
        store_provider_code: 'lidl',
        store_label: 'Lidl',
        purchase_date: '2026-07-25',
        import_status: 'review',
        lines: [{
          id: lineId,
          article_name_raw: 'MOSTERD 250G',
          quantity_raw: 1,
          unit_raw: 'stuk',
          processing_status: 'pending',
          review_decision: 'pending',
          match_status: saved ? 'matched' : 'unmatched',
          matched_household_article_id: householdArticleId,
          matched_global_product_id: saved ? 'gp-mosterd' : null,
          matched_global_product_name: saved ? 'Mosterd Dijon' : null,
        }],
      }),
    }));

    await page.route('**/api/barcodes/validate', async (route) => {
      expect(route.request().method()).toBe('POST');
      expect(await route.request().postDataJSON()).toEqual({
        value: gtin,
        declared_type: 'gtin',
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          valid: true,
          normalized_value: gtin,
          declared_type: 'gtin',
          mutated: false,
        }),
      });
    });

    await page.route(`**/api/barcodes/${gtin}`, async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        valid: true,
        gtin,
        match_status: 'not_found',
        product: null,
        identity: null,
        product_type: null,
        mutated: false,
      }),
    }));

    await page.route(
      `**/api/barcodes/${gtin}/save-household-article`,
      async (route) => {
        expect(route.request().method()).toBe('POST');
        expect(await route.request().postDataJSON()).toEqual({
          purchase_import_line_id: lineId,
          household_article_id: householdArticleId,
          article_name: 'MOSTERD 250G',
        });

        saved = true;

        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ok: true,
            gtin,
            catalog_product_created: true,
            product: {
              global_product_id: 'gp-mosterd',
              name: 'Mosterd Dijon',
              primary_gtin: gtin,
              status: 'active',
            },
            purchase_import_line_id: lineId,
            household_article_id: householdArticleId,
            inventory_mutated: false,
          }),
        });
      }
    );

    await page.goto(`/kassabonnen?batch=${batchId}`);
    await page.getByTestId(`receipt-line-${lineId}`).locator('td').nth(1).dblclick();

    await page.getByTestId(`receipt-line-barcode-input-${lineId}`).fill(gtin);
    await page.getByTestId(`receipt-line-barcode-check-${lineId}`).click();

    const confirm = page.getByTestId('receipt-line-barcode-save-confirm');
    await expect(confirm).toBeVisible();
    await expect(confirm).toContainText('De barcode is geldig.');

    await page.getByTestId('receipt-line-barcode-save-cancel').click();
    await expect(confirm).toHaveCount(0);
    expect(mutationRequests).toEqual([]);

    await page.getByTestId(`receipt-line-barcode-check-${lineId}`).click();
    await expect(confirm).toBeVisible();
    await page.getByTestId('receipt-line-barcode-save-confirm-button').click();

    await expect(confirm).toHaveCount(0);
    await expect(page.getByTestId('app-feedback-success')).toContainText(
      'Product opgenomen in de catalogus en bijgewerkt in Uitpakken.'
    );
    await expect(
      page.getByTestId(`receipt-line-standard-product-${lineId}`)
    ).toHaveValue('Mosterd Dijon');

    expect(
      mutationRequests.some(
        (request) => request.includes(
          `/api/barcodes/${gtin}/save-household-article`
        )
      )
    ).toBe(true);

    expect(
      mutationRequests.some(
        (request) => /inventory/.test(request)
      )
    ).toBe(false);

    await expectNoConsoleErrors(consoleErrors);
  });

});

