import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

async function routeProductGroups(page) {
  await page.route('**/api/inventory/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          {
            inventory_group_key: 'saus.mosterd',
            display_name: 'Mosterd',
            base_unit: 'kg',
            total_normalized_quantity: 0,
            known_quantity_items: 0,
            unknown_quantity_items: 1,
            item_count: 1,
            locations: ['Kelderkast'],
            products: [],
            confidence: 0.25,
          },
        ],
        unresolved_items: [
          { inventory_id: 'test-boor', product_name: 'Boormachine', stock_quantity: 1, reason: 'no_inventory_group_match' },
        ],
        total_groups: 1,
        total_unresolved_items: 1,
        source: 'inventory_group_projection_v1',
        mutates_inventory: false,
      }),
    });
  });
  await page.route('**/api/admin/inventory/groups/ensure-schema', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, schema: 'product_inventory_groups', seed: 'm2c2i30a_seed', mutates_inventory: false }),
    });
  });
}

test.describe('Productgroepen frontend-regressie', () => {
  test('Landingspagina toont Productgroepen en opent beheerpagina', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeProductGroups(page);

    await page.goto('/home');
    await expect(page.getByText('Productgroepen', { exact: true })).toBeVisible();
    await page.getByText('Productgroepen', { exact: true }).click();

    await expect(page).toHaveURL(/\/productgroepen$/);
    await expect(page.getByTestId('product-groups-page')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Productgroepen' })).toBeVisible();
    await expect(page.getByTestId('product-groups-table')).toContainText('Mosterd');
    await expect(page.getByTestId('product-groups-unresolved-table')).toContainText('Boormachine');
    await expect(page.getByText('Nee', { exact: true })).toBeVisible();
    await expectNoConsoleErrors(consoleErrors);
  });
});
