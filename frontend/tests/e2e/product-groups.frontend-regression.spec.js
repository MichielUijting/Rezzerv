import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

async function routeProductGroups(page) {
  let assigned = false;
  const groupOptions = [
    { inventory_group_key: 'saus.mosterd', display_name: 'Mosterd extra lange productgroepnaam', default_base_unit: 'kg' },
  ];
  await page.route('**/api/inventory/groups', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        items: [
          {
            inventory_group_key: 'saus.mosterd',
            display_name: 'Mosterd extra lange productgroepnaam',
            base_unit: 'kg',
            item_count: assigned ? 2 : 1,
            products: [
              { inventory_id: 'test-mosterd', product_name: 'Mosterd fijne Dijon extra lange artikelnaam', stock_quantity: 1 },
              ...(assigned ? [{ inventory_id: 'test-boor', product_name: 'Boormachine met zeer lange artikelnaam', stock_quantity: 1 }] : []),
            ],
          },
        ],
        group_options: groupOptions,
        unresolved_items: assigned ? [] : [
          { inventory_id: 'test-boor', product_name: 'Boormachine met zeer lange artikelnaam', stock_quantity: 1, reason: 'no_inventory_group_match' },
        ],
        total_groups: 1,
        total_unresolved_items: assigned ? 0 : 1,
        source: 'inventory_group_projection_v1',
        mutates_inventory: false,
      }),
    });
  });
  await page.route('**/api/product-groups', async (route) => {
    if (route.request().method() === 'POST') {
      groupOptions.push({ inventory_group_key: 'productgroep.soep', display_name: 'Soep', default_base_unit: 'stuk' });
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, inventory_group_key: 'productgroep.soep', display_name: 'Soep', default_base_unit: 'stuk', mutates_inventory: false }) });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/product-groups/saus.mosterd', async (route) => {
    if (route.request().method() === 'PUT') {
      groupOptions[0] = { inventory_group_key: 'saus.mosterd', display_name: 'Mosterd bijgewerkt', default_base_unit: 'kg' };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, inventory_group_key: 'saus.mosterd', display_name: 'Mosterd bijgewerkt', default_base_unit: 'kg', mutates_inventory: false }) });
      return;
    }
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, inventory_group_key: 'saus.mosterd', mutates_inventory: false }) });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/inventory/items/test-boor/group', async (route) => {
    assigned = true;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, inventory_id: 'test-boor', inventory_group_key: 'saus.mosterd', mutates_inventory: false }) });
  });
}

test.describe('Productgroepen frontend-regressie', () => {
  test('Landingspagina opent beheergrid conform Uitpakken en beheert productgroepen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    await routeProductGroups(page);

    await page.goto('/home');
    await expect(page.getByText('Productgroepen', { exact: true })).toBeVisible();
    await page.getByText('Productgroepen', { exact: true }).click();

    await expect(page).toHaveURL(/\/productgroepen$/);
    await expect(page.getByTestId('product-groups-page')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Terug' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Groepen controleren' })).toHaveCount(0);

    const table = page.getByTestId('product-groups-table');
    await expect(table.locator('thead tr').first()).toContainText('Artikel');
    await expect(table.locator('thead tr').first()).toContainText('Productgroep');
    await expect(table.locator('thead tr').first()).toContainText('Bevestigen');
    await expect(table.locator('thead tr').nth(1)).toContainText('Zoek');
    await expect(table.locator('thead tr').nth(1)).toContainText('Filter');
    await expect(table.locator('thead')).not.toContainText('Eenheid');
    await expect(table.locator('thead')).not.toContainText('Status');
    await expect(table.locator('thead')).not.toContainText('Actie');
    await expect(table).toContainText('Mosterd fijne Dijon extra lange artikelnaam');
    await expect(table).toContainText('Boormachine met zeer lange artikelnaam');

    await page.getByLabel('Zoek artikel').fill('boor');
    await expect(table).toContainText('Boormachine met zeer lange artikelnaam');
    await expect(table).not.toContainText('Mosterd fijne Dijon extra lange artikelnaam');
    await page.getByLabel('Zoek artikel').fill('');

    await expect(page.getByLabel('Bestaande productgroep')).toBeVisible();
    await expect(page.getByLabel('Productgroepnaam')).toBeVisible();
    await expect(page.getByLabel('Eenheid productgroep')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Toevoegen' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Bijwerken' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Verwijderen' })).toBeVisible();

    await page.getByLabel('Productgroepnaam').fill('Soep');
    await page.getByRole('button', { name: 'Toevoegen' }).click();
    await expect(page.getByTestId('product-groups-feedback-success')).toContainText('Productgroep is toegevoegd.');
    await page.getByTestId('product-groups-feedback-success-ok-button').click();

    await page.getByLabel('Productgroep voor Boormachine met zeer lange artikelnaam').selectOption('saus.mosterd');
    await page.getByRole('button', { name: 'Bevestigen' }).click();
    await expect(page.getByTestId('product-groups-feedback-success')).toContainText('Artikel is aan de productgroep toegevoegd.');
    await page.getByTestId('product-groups-feedback-success-ok-button').click();
    await expectNoConsoleErrors(consoleErrors);
  });
});
