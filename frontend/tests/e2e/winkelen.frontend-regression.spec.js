import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';


test.describe('Winkelen Release 1 frontend-regressie', () => {
  test('lege lijst, toevoegen, afvinken, verwijderen en afronden', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let activeListId = 'shopping-list-active-1';
    let items = [];

    await page.route('**/api/shopping-list', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: activeListId,
          household_id: '0',
          status: 'active',
          items,
          item_count: items.length,
        }),
      });
    });

    await page.route('**/api/shopping-list/items', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback();
      const payload = JSON.parse(route.request().postData() || '{}');
      const item = {
        id: `shopping-item-${items.length + 1}`,
        shopping_list_id: activeListId,
        household_id: '0',
        article_name: payload.article_name,
        quantity: Number(payload.quantity),
        volume: Number(payload.volume),
        unit: payload.unit,
        note: payload.note,
        checked: false,
        source_type: 'manual',
      };
      items = [...items, item];
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(item) });
    });

    await page.route('**/api/shopping-list/items/*', async (route) => {
      const itemId = route.request().url().split('/').pop();
      if (route.request().method() === 'PUT') {
        const patch = JSON.parse(route.request().postData() || '{}');
        items = items.map((item) => item.id === itemId ? { ...item, ...patch } : item);
        const updated = items.find((item) => item.id === itemId);
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(updated) });
        return;
      }
      if (route.request().method() === 'DELETE') {
        items = items.filter((item) => item.id !== itemId);
        await route.fulfill({ status: 204, body: '' });
        return;
      }
      await route.fallback();
    });

    await page.route('**/api/shopping-list/complete', async (route) => {
      const completedListId = activeListId;
      const completedItemCount = items.length;
      activeListId = 'shopping-list-active-2';
      items = [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'completed',
          completed_list_id: completedListId,
          completed_item_count: completedItemCount,
          active_list_id: activeListId,
          items: [],
        }),
      });
    });

    await page.goto('/winkelen');
    await expect(page).toHaveURL(/\/winkelen$/);
    await expect(page.getByTestId('shopping-page')).toBeVisible();
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Winkelen afgerond' })).toBeDisabled();

    await page.getByLabel('Artikel').fill('Melk');
    await page.getByLabel('Aantal').fill('2');
    await page.getByLabel('Volume').fill('1.5');
    await page.getByLabel('Eenheid').selectOption('liter');
    await page.getByLabel('Opmerking').fill('Halfvol');
    await page.getByRole('button', { name: 'Toevoegen' }).click();

    await expect(page.getByText('Melk', { exact: true })).toBeVisible();
    await expect(page.getByTestId('shopping-list-table')).toContainText('2');
    await expect(page.getByTestId('shopping-list-table')).toContainText('1,5');
    await expect(page.getByTestId('shopping-list-table')).toContainText('Halfvol');

    await page.getByLabel('Gekocht Melk').check();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();

    await page.reload();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();

    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Verwijderen' }).click();
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();

    await page.getByLabel('Artikel').fill('Brood');
    await page.getByRole('button', { name: 'Toevoegen' }).click();
    await expect(page.getByText('Brood', { exact: true })).toBeVisible();

    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Winkelen afgerond' }).click();
    await expect(page.getByText('Winkelen is afgerond. De winkellijst is leeggemaakt.')).toBeVisible();
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Winkelen afgerond' })).toBeDisabled();

    await expectNoConsoleErrors(consoleErrors);
  });
});
