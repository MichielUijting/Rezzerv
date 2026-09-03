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
});
