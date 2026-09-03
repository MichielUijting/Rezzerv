import { test, expect } from '@playwright/test';

test.describe('Uitpakken zonder locaties', () => {
  test('verbergt locatiebediening en verwerkt de geselecteerde regel naar voorraad', async ({ page }) => {
    const batchId = 'locationless-uitpakken-batch';
    const lineId = 'locationless-uitpakken-line';
    let processed = false;
    let reviewDecision = 'pending';
    let processPayload = null;

    await page.route('**/api/session', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: { id: 'locationless-admin', email: 'locationless@example.com' },
        user_id: 'locationless-admin',
        email: 'locationless@example.com',
        active_household_id: '1',
        active_household_name: 'Locationless huishouden',
        context_type: 'regular',
        role: 'admin',
        display_role: 'admin',
        household_role: 'household.admin',
        permissions: {},
        supported_permissions: [],
        is_viewer: false,
        is_platform_superuser: false,
        is_frontteam: false,
      }),
    }));

    await page.route('**/api/onboarding/capabilities', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        active_use_cases: ['wat_inhuis'],
        product_configuration: {
          inventory_tracking_level: 'presence',
          location_tracking_level: 'none',
          receipt_processing_enabled: true,
        },
      }),
    }));

    await page.route('**/api/onboarding', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    }));

    await page.route('**/api/household', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '1',
        active_household_id: '1',
        is_viewer: false,
        role: 'admin',
        display_role: 'admin',
        store_import_simplification_level: 'gebalanceerd',
      }),
    }));

    await page.route('**/api/store-providers', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ code: 'ah', name: 'Albert Heijn' }]),
    }));

    await page.route('**/api/store-review-articles', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{ id: 'article-gehakt', name: 'M Gehakt' }]),
    }));

    await page.route('**/api/article-groups*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }));

    await page.route('**/api/spaces*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [{ id: 'berging', naam: 'Berging', active: true }] }),
    }));

    await page.route('**/api/sublocations*', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [{ id: 'voorraadkast', naam: 'Voorraadkast', space_id: 'berging', active: true }] }),
    }));

    await page.route('**/api/households/1/articles/inventory-handling/batch', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [{ id: 'article-gehakt', default_inventory_handling: 'STOCK' }] }),
    }));

    await page.route('**/api/households/1/purchase-import-lines/inventory-handling-overrides/batch', async (route) => route.fulfill({
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
          store_provider_code: 'ah',
          store_label: 'Albert Heijn',
          purchase_date: '2026-03-26',
          inbox_status: 'Gecontroleerd',
          summary: { total: 1 },
        }],
      }),
    }));

    await page.route(`**/api/purchase-import-lines/${lineId}/review`, async (route) => {
      const payload = await route.request().postDataJSON();
      reviewDecision = String(payload?.review_decision || 'pending');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, review_decision: reviewDecision }),
      });
    });

    await page.route(`**/api/purchase-import-batches/${batchId}/process`, async (route) => {
      processPayload = await route.request().postDataJSON();
      processed = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          processed_count: 1,
          skipped_count: 0,
          failed_count: 0,
          results: [{ line_id: lineId, status: 'processed', event_id: 'event-1' }],
        }),
      });
    });

    await page.route(`**/api/purchase-import-batches/${batchId}*`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          batch_id: batchId,
          household_id: '1',
          store_provider_code: 'ah',
          store_label: 'Albert Heijn',
          purchase_date: '2026-03-26',
          import_status: processed ? 'processed' : 'review',
          lines: [{
            id: lineId,
            article_name_raw: 'AH M GEHAKT',
            quantity_raw: 1,
            unit_raw: 'stuk',
            matched_household_article_id: 'article-gehakt',
            suggested_household_article_id: 'article-gehakt',
            resolved_household_article_name: 'M Gehakt',
            selected_article_group_id: null,
            target_location_id: 'voorraadkast',
            processing_status: processed ? 'processed' : 'failed',
            processing_error: processed ? null : 'oude locatie-instelling',
            review_decision: reviewDecision,
            match_status: 'matched',
          }],
        }),
      });
    });

    await page.goto(`/kassabonnen?batch=${batchId}`);

    const lineRow = page.getByTestId(`receipt-line-${lineId}`);
    const receiptLinesTable = page.getByTestId('receipt-lines-table');
    await expect(lineRow).toBeVisible();
    await expect(page.getByTestId('receipt-bulk-location-button')).toBeHidden();
    await expect(receiptLinesTable.locator('th[aria-label="Locatie sorteren"]')).toBeHidden();
    await expect(receiptLinesTable.locator('select[aria-label="Filter op locatie"]')).toBeHidden();

    const lineSelection = page.getByTestId(`receipt-line-select-${lineId}`);
    await lineSelection.check();
    await expect(lineSelection).toBeChecked();

    await page.getByTestId('receipt-process-button').click();

    await expect(page.getByRole('dialog', { name: 'Niet alle geselecteerde regels zijn compleet' })).toHaveCount(0);
    await expect.poll(() => reviewDecision).toBe('selected');
    await expect.poll(() => processPayload).not.toBeNull();
    expect(processPayload).toEqual({ processed_by: 'ui', mode: 'selected_only' });
    await expect(lineRow).toHaveCount(0);
    await expect(page.getByText(/target_location_id is niet toegestaan/i)).toHaveCount(0);
  });
});