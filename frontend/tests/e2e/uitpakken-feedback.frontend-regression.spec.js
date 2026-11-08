import { test, expect } from '@playwright/test';

test.describe('Uitpakken melding-overlay regressie', () => {
  test('API-fout in kassabonnenlijst gebruikt standaard Melding-overlay zonder valse leegstaat', async ({ page }) => {
    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          authenticated: true,
          user: { id: 'uitpakken-feedback-admin', email: 'uitpakken-feedback-admin@example.com' },
          user_id: 'uitpakken-feedback-admin',
          email: 'uitpakken-feedback-admin@example.com',
          active_household_id: 'household-feedback',
          active_household_name: 'Uitpakken huishouden',
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
      });
    });

    await page.route('**/api/onboarding', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    }));

    await page.route('**/api/household', async (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'household-feedback',
        active_household_id: 'household-feedback',
        name: 'Uitpakken huishouden',
        is_viewer: false,
        permissions: {},
      }),
    }));

    let unpackCalls = 0;
    await page.route('**/api/unpack-start-batches*', async (route) => {
      unpackCalls += 1;
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Interne serverfout in de API' }),
      });
    });

    await page.goto('/kassabonnen');

    const feedback = page.getByTestId('app-feedback-error');
    await expect(feedback).toBeVisible();
    await expect(feedback.getByText('Melding', { exact: true })).toBeVisible();
    await expect(feedback).toContainText('Interne serverfout in de API');
    await expect(page.getByTestId('app-feedback-error-ok-button')).toBeVisible();
    await expect(page.getByTestId('receipts-page').locator('.rz-inline-feedback')).toHaveCount(0);
    await expect(page.getByText('Er zijn nog geen kassabonnen.')).toHaveCount(0);
    expect(unpackCalls).toBe(1);

    await page.getByTestId('app-feedback-error-ok-button').click();
    await expect(page.getByTestId('app-feedback-error-overlay')).toHaveCount(0);
  });
  test('bulk Goedkeuren zonder locaties toont geen standaardlocatie-eis en fouten via OK-overlay', async ({ page }) => {
    await page.route('**/api/session', async (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        authenticated: true,
        user: { id: 'locatievrij-admin', email: 'locatievrij@example.com' },
        user_id: 'locatievrij-admin', email: 'locatievrij@example.com',
        active_household_id: 'h-locationless',
        active_household_name: 'Zonder locaties',
        context_type: 'regular', role: 'admin', display_role: 'admin',
        household_role: 'household.admin', permissions: {}, supported_permissions: [],
        is_viewer: false, is_platform_superuser: false, is_frontteam: false,
      }),
    }));
    await page.route('**/api/household', async (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ id: 'h-locationless', active_household_id: 'h-locationless' }),
    }));
    await page.route('**/api/onboarding', async (route) => route.fulfill({
      status: 200, contentType: 'application/json', body: '{}',
    }));
    await page.route('**/api/unpack-start-batches*', async (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ total: 1, items: [{
        batch_id: 'existing-receipt', store_provider_code: 'ah',
        store_label: 'Albert Heijn', purchase_date: '2026-11-07',
        inbox_status: 'Gecontroleerd', summary: { total: 1 },
      }] }),
    }));
    const calls = [];
    await page.route('**/api/purchase-import-batches/existing-receipt', async (route) => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ batch_id: 'existing-receipt', lines: [
        { id: 'ah-mango', article_name_raw: 'AH MANGO', quantity_raw: 1,
          review_decision: 'selected', processing_status: 'pending',
          matched_household_article_id: null, matched_global_product_id: null },
        { id: 'ignored', article_name_raw: 'EMBALLAGE', quantity_raw: 1,
          review_decision: 'ignored', processing_status: 'pending',
          matched_household_article_id: null, matched_global_product_id: null },
        { id: 'processed', article_name_raw: 'VOORRAAD AL VERWERKT', quantity_raw: 1,
          review_decision: 'selected', processing_status: 'processed',
          matched_household_article_id: null, matched_global_product_id: null },
      ] }),
    }));
    await page.route('**/api/purchase-import-lines/*/create-article', async (route) => {
      calls.push({ kind: 'create', path: route.request().url(), body: await route.request().postDataJSON() });
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    let requestedMode = '';
    await page.route('**/api/purchase-import-batches/existing-receipt/process', async (route) => {
      calls.push({ kind: 'process' });
      requestedMode = (await route.request().postDataJSON()).mode;
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          processed_count: 0, skipped_count: 0, failed_count: 1,
        }),
      });
    });
    await page.goto('/kassabonnen');
    await page.getByTestId('receipt-batch-row-existing-receipt').locator('input[type="checkbox"]').check();
    await page.getByTestId('unpack-approve-selected-button').click();
    await expect.poll(() => requestedMode).toBe('ready_only');
    expect(calls.map((call) => call.kind)).toEqual(['create', 'process']);
    expect(calls[0].path).toContain('/api/purchase-import-lines/ah-mango/create-article');
    expect(calls[0].body).toEqual({ article_name: 'AH MANGO' });
    const errorOverlay = page.getByTestId('app-feedback-error');
    await expect(errorOverlay).toBeVisible();
    await expect(errorOverlay).toContainText('Mislukt: 1');
    await expect(errorOverlay).not.toContainText('standaardlocatie');
    await expect(page.getByTestId('app-feedback-error-ok-button')).toBeVisible();
    await page.getByTestId('app-feedback-error-ok-button').click();
    await expect(page.getByTestId('app-feedback-error-overlay')).toHaveCount(0);
  });

});
