import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectAnyVisible,
  expectNoConsoleErrors,
  expectRouteLoads,
} from './helpers/rezzervAssertions';
import { apiFetch, resolveAuthorizedHouseholdId } from './helpers/devApi';

test.describe('Uitpakken frontend-regressie', () => {
  test('PostgreSQL Uitpakken-routes blijven SQL-portabel', async ({ page }) => {
    const householdId = await resolveAuthorizedHouseholdId(page.request);

    const batches = await apiFetch(
      page.request,
      `/api/unpack-start-batches?householdId=${encodeURIComponent(householdId)}`
    );
    const reviewArticles = await apiFetch(page.request, '/api/store-review-articles');

    expect(Array.isArray(batches?.items)).toBe(true);
    expect(Array.isArray(reviewArticles)).toBe(true);
  });

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
    await expect(page).toHaveURL(new RegExp(`/kassabonnen/batch/${batchId}$`));

    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('Kassabon Kassabon')).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Bonregels', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Diagnose', exact: true })).toBeVisible();
    await expect(page.getByTestId('receipt-detail-title')).toHaveCount(1);

    await expectNoConsoleErrors(consoleErrors);
  });

  test('Oude bonartikeldetailroute verwijst naar volledig Uitpakken', async ({ page }) => {
    await page.goto('/kassabonnen/batch/legacy-batch/regel/legacy-line');
    await expect(page).toHaveURL(/\/kassabonnen\?batch=legacy-batch$/);
    await expect(page.getByText('Kassabon Kassabon')).toHaveCount(0);
  });

  test('Locatiebeheer blijft als route beschikbaar voor uitpakken-flow', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          user: { id: 'uitpakken-settings-admin', email: 'uitpakken-settings-admin@example.com' },
          user_id: 'uitpakken-settings-admin',
          email: 'uitpakken-settings-admin@example.com',
          active_household_id: '1',
          active_household_name: 'Uitpakken huishouden',
          context_type: 'regular',
          role: 'admin',
          display_role: 'admin',
          household_role: 'household.admin',
          permissions: { 'locations.manage': true },
          supported_permissions: ['locations.manage'],
          is_viewer: false,
          is_platform_superuser: false,
          is_frontteam: false,
        }),
      });
    });
    await page.route('**/api/onboarding', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    }));
    await page.route('**/api/spaces', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }));
    await page.route('**/api/sublocations', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }));

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
          id: '0',
          active_household_id: '0',
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
            summary: { total: 2 },
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
      const isReadOnlyHandlingBatch =
        /\/articles\/inventory-handling\/batch(?:\?|$)/.test(url)
        || /\/purchase-import-lines\/inventory-handling-overrides\/batch(?:\?|$)/.test(url);
      if (
        !isReadOnlyHandlingBatch
        && /inventory|purchase|external-product-links|household-articles|save-household-article/.test(url)
        && request.method() !== 'GET'
      ) {
        mutationRequests.push(`${request.method()} ${url}`);
      }
    });

    await page.route('**/api/household', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '0',
        active_household_id: '0',
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
          matched_global_product_gtin: saved ? gtin : null,
          barcode: saved ? gtin : null,
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
    await expect(confirm).toContainText('Dit is een geldige barcode.');
    await expect(
      page.getByTestId(`receipt-line-barcode-status-${lineId}`)
    ).toHaveCount(0);

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
    await expect(
      page.getByTestId(`receipt-line-barcode-input-${lineId}`)
    ).toHaveValue(gtin);
    await expect(
      page.getByTestId(`receipt-line-barcode-status-${lineId}`)
    ).toHaveCount(0);

    const successOverlay = page.getByTestId(
      'app-feedback-success-overlay'
    );

    if (await successOverlay.count()) {
      const feedbackButton = successOverlay.getByRole(
        'button',
        { name: /ok|sluiten/i }
      );

      if (await feedbackButton.count()) {
        await feedbackButton.click();
      } else {
        await successOverlay.click({
          position: { x: 5, y: 5 },
        });
      }

      await expect(successOverlay).toHaveCount(0);
    }

    await page.getByRole(
      'button',
      { name: 'Sluit bonartikeldetails' }
    ).click();

    await expect(
      page.getByTestId('receipt-line-detail-overlay')
    ).toHaveCount(0);

    await page.getByTestId(`receipt-line-${lineId}`)
      .locator('td')
      .nth(1)
      .dblclick();

    await expect(
      page.getByTestId(`receipt-line-barcode-input-${lineId}`)
    ).toHaveValue(gtin);

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


  test('Mobiele Beheerder kan vanuit Uitpakken inline een nieuwe locatie toevoegen', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    const batchId = 'mobile-inline-location-create';
    const lineId = 'mobile-inline-location-line';
    const readyLineId = 'mobile-ready-line';
    const spaces = [{ id: 'space-keuken', naam: 'Keuken', active: true }];
    const targetLocationWrites = [];

    await page.route('**/api/**', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const path = url.pathname;
      const method = request.method();
      const json = (body, status = 200) => route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

      const adminPermissions = {
        'admin.access': true,
        'locations.manage': true,
        'article.create': true,
        'receipts.process': true,
      };

      if (path === '/api/session' && method === 'GET') {
        return json({
          user_id: 'mobile-admin',
          email: 'mobile-admin@rezzerv.test',
          active_household_id: '1',
          active_household_name: 'Mobiel huishouden',
          context_type: 'regular',
          role: 'admin',
          display_role: 'Beheerder',
          membership_count: 1,
          can_switch_households: false,
          memberships: [{ household_id: '1', role: 'admin' }],
          permissions: adminPermissions,
          is_viewer: false,
          can_process_receipts: true,
          is_platform_superuser: false,
        });
      }

      if (path === '/api/household' && method === 'GET') {
        return json({
          id: '1',
          active_household_id: '1',
          display_role: 'Beheerder',
          role: 'admin',
          is_viewer: false,
          permissions: adminPermissions,
          location_tracking_level: 'global',
          store_import_simplification_level: 'gebalanceerd',
        });
      }

      if (path === '/api/store-providers' && method === 'GET') return json([{ code: 'lidl', name: 'Lidl' }]);
      if (path === '/api/store-review-articles' && method === 'GET') return json([{ id: 'article-mosterd', name: 'Mosterd', label: 'Mosterd' }]);
      if (path === '/api/spaces' && method === 'GET') return json({ items: spaces });
      if (path === '/api/sublocations' && method === 'GET') return json({ items: [] });

      if (path === '/api/spaces' && method === 'POST') {
        const body = request.postDataJSON();
        spaces.push({ id: 'space-garage', naam: body.naam, active: true });
        return json({ ok: true });
      }

      if (path === '/api/unpack-start-batches' && method === 'GET') {
        return json({
          items: [{
            batch_id: batchId,
            store_provider_code: 'lidl',
            store_label: 'Lidl',
            purchase_date: '2026-10-07',
            inbox_status: 'Gecontroleerd',
            summary: { total: 1 },
          }],
        });
      }

      if (path === `/api/purchase-import-batches/${batchId}` && method === 'GET') {
        return json({
          batch_id: batchId,
          store_provider_code: 'lidl',
          store_label: 'Lidl',
          purchase_date: '2026-10-07',
          import_status: 'review',
          household_id: '1',
          lines: [{
            id: lineId,
            article_name_raw: 'MOSTERD',
            quantity_raw: 1,
            unit_raw: 'stuk',
            matched_household_article_id: 'article-mosterd',
            suggested_household_article_id: 'article-mosterd',
            resolved_household_article_name: 'Mosterd',
            target_location_id: '',
            processing_status: 'pending',
            review_decision: 'selected',
            match_status: 'matched',
          }, {
            id: readyLineId,
            article_name_raw: 'PASTA',
            quantity_raw: 1,
            unit_raw: 'stuk',
            matched_household_article_id: 'article-mosterd',
            suggested_household_article_id: 'article-mosterd',
            resolved_household_article_name: 'Pasta',
            target_location_id: 'space-keuken',
            processing_status: 'pending',
            review_decision: 'selected',
            match_status: 'matched',
          }],
        });
      }

      if (path === `/api/purchase-import-lines/${lineId}/target-location` && method === 'POST') {
        const body = request.postDataJSON();
        targetLocationWrites.push(body);
        return json({ ok: true, target_location_id: body.target_location_id });
      }

      if (path === '/api/households/1/articles/inventory-handling/batch' && method === 'POST') {
        return json({ items: [{ id: 'article-mosterd', default_inventory_handling: 'STOCK' }] });
      }
      if (path === '/api/households/1/purchase-import-lines/inventory-handling-overrides/batch' && method === 'POST') {
        return json({ items: [] });
      }
      if (path === `/api/households/1/purchase-import-lines/${lineId}/inventory-handling-override` && method === 'PUT') {
        return json({ inventory_handling_override: request.postDataJSON().inventory_handling_override });
      }

      if (path === '/api/article-groups' && method === 'GET') return json({ items: [] });
      if (method === 'GET') return json({ items: [] });
      return json({ ok: true });
    });

    await page.goto(`/kassabonnen/batch/${batchId}`);

    await expect(page.getByRole('tab', { name: 'Bonregels', exact: true })).toHaveCount(0);
    await expect(page.getByRole('tab', { name: 'Diagnose', exact: true })).toHaveCount(0);
    await expect(page.getByTestId('mobile-unpack-search-filter-input')).toBeVisible();
    await expect(page.getByTestId('mobile-unpack-status-filter')).toHaveCount(0);
    await expect(page.getByTestId('mobile-unpack-mapping-filter')).toHaveCount(0);
    await expect(page.getByTestId('mobile-unpack-location-filter')).toHaveCount(0);
    await expect(page.getByTestId('receipt-export-button')).toHaveCount(0);
    await expect(page.getByTestId('mobile-unpack-receipt-title')).toHaveText('Lidl · 2026-10-07');
    await expect(page.getByText(/Status:.*Vereenvoudigingsniveau:/)).toHaveCount(0);
    await expect(page.getByText(/^Totaal:/)).toHaveCount(0);
    await expect(page.getByTestId('receipt-bulk-location-button')).toHaveText('Pas standaardlocatie toe');

    const selectAll = page.getByTestId('mobile-unpack-select-all-lines').getByRole('checkbox');
    await expect(selectAll).toBeVisible();
    await selectAll.check();
    await expect(page.getByTestId(`receipt-line-select-${lineId}`)).toBeChecked();
    await expect(page.getByTestId(`receipt-line-select-${readyLineId}`)).toBeChecked();

    await expect(page.getByTestId(`receipt-line-${lineId}`)).toHaveClass(/rz-mobile-unpack-row--action-needed/);
    await expect(page.getByTestId(`receipt-line-${readyLineId}`)).toHaveClass(/rz-mobile-unpack-row--ready/);

    const combinedFilter = page.getByTestId('mobile-unpack-search-filter-input');
    await combinedFilter.fill('actie nodig');
    await expect(page.getByTestId(`receipt-line-${lineId}`)).toBeVisible();
    await combinedFilter.fill('');

    const inlineCreate = page.getByTestId(`mobile-unpack-add-location-${lineId}`);
    await expect(inlineCreate).toBeVisible();
    await expect(inlineCreate).toContainText('Nieuwe locatie / sublocatie');

    await inlineCreate.click();

    await expect(page.getByRole('dialog', { name: 'Locatie / sublocatie kiezen' })).toBeVisible();
    await expect(page.getByTestId('receipt-location-create-space')).toBeVisible();
    await expect(page.getByTestId('receipt-location-create-sublocation')).toBeVisible();

    await page.getByTestId('receipt-location-create-space').click();
    await page.getByTestId('receipt-location-create-name').fill('Garage');
    await page.getByTestId('receipt-location-create-save').click();

    await expect.poll(() => spaces.map((space) => space.naam)).toContain('Garage');
    await expect.poll(() => targetLocationWrites.map((write) => write.target_location_id)).toContain('space-garage');
  });

});