import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';


test.describe('Winkelen Release 1 frontend-regressie', () => {
  test('catalogus zoeken, toevoegen, inline aanvullen, afvinken en afronden', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let activeListId = 'shopping-list-active-1';
    let items = [];

    const candidates = {
      household_articles: [{
        source_type: 'household_article',
        source_id: 'household-article-melk',
        label: 'Melk',
        article_name: 'Melk',
        article_group_name: 'Zuivel',
        product_type_name: 'Halfvolle melk',
      }],
      product_types: [{
        source_type: 'product_type',
        source_id: 'product-type-brood',
        label: 'Brood',
        article_name: 'Brood',
        article_group_name: '',
        product_type_name: 'Brood',
      }],
      article_groups: [{
        source_type: 'article_group',
        source_id: 'article-group-fruit',
        label: 'Fruit',
        article_name: 'Fruit',
        article_group_name: 'Fruit',
        product_type_name: '',
      }],
    };

    await page.route('**/api/shopping-list/catalog-search?*', async (route) => {
      const url = new URL(route.request().url());
      const scope = url.searchParams.get('scope');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scope, query: url.searchParams.get('query'), items: candidates[scope] || [], total: (candidates[scope] || []).length }),
      });
    });

    await page.route('**/api/shopping-list', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: activeListId, household_id: '0', status: 'active', items, item_count: items.length }),
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
        article_group_name: payload.article_group_name || '',
        product_type_name: payload.product_type_name || '',
        quantity: null,
        volume: null,
        unit: '',
        note: '',
        checked: false,
        source_type: payload.source_type,
        source_id: payload.source_id,
      };
      items = [...items, item];
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(item) });
    });

    await page.route('**/api/shopping-list/items/*', async (route) => {
      const itemId = route.request().url().split('/').pop();
      if (route.request().method() !== 'PUT') return route.fallback();
      const patch = JSON.parse(route.request().postData() || '{}');
      items = items.map((item) => item.id === itemId ? { ...item, ...patch } : item);
      const updated = items.find((item) => item.id === itemId);
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(updated) });
    });

    await page.route('**/api/shopping-list/complete', async (route) => {
      const completedListId = activeListId;
      const completedItemCount = items.length;
      activeListId = 'shopping-list-active-2';
      items = [];
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'completed', completed_list_id: completedListId, completed_item_count: completedItemCount, active_list_id: activeListId, items: [] }),
      });
    });

    await page.goto('/winkelen');
    await expect(page).toHaveURL(/\/winkelen$/);
    await expect(page.getByTestId('shopping-page')).toBeVisible();
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Afsluiten' })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: 'Actie' })).toHaveCount(0);
    await expect(page.getByTestId('shopping-list-table')).toHaveClass(/rz-table--resizable-columns/);

    await page.getByLabel('Zoeken in', { exact: true }).selectOption('household_articles');
    await page.getByLabel('Catalogus zoeken').fill('melk');
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Melk');
    await page.getByLabel('Zoekresultaat').selectOption('household_article:household-article-melk');
    await page.getByRole('button', { name: 'Toevoegen' }).click();

    await expect(page.getByText('Melk', { exact: true })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Zuivel', exact: true })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Halfvolle melk', exact: true })).toBeVisible();

    await page.getByLabel('Aantal Melk').fill('2');
    await page.getByLabel('Aantal Melk').blur();
    await page.getByLabel('Volume Melk').fill('1,5');
    await page.getByLabel('Volume Melk').blur();
    await page.getByLabel('Eenheid Melk').selectOption('liter');
    await page.getByLabel('Opmerking Melk').fill('Halfvol');
    await page.getByLabel('Opmerking Melk').blur();

    await page.getByLabel('Gekocht Melk').check();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();
    await page.reload();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();
    await expect(page.getByLabel('Aantal Melk')).toHaveValue('2');
    await expect(page.getByLabel('Volume Melk')).toHaveValue('1,5');
    await expect(page.getByLabel('Eenheid Melk')).toHaveValue('liter');
    await expect(page.getByLabel('Opmerking Melk')).toHaveValue('Halfvol');

    await page.getByLabel('Filter artikelgroep').selectOption('Zuivel');
    await expect(page.getByText('Melk', { exact: true })).toBeVisible();
    await page.getByLabel('Zoeken in winkellijst').fill('onbekend');
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();
    await page.getByLabel('Zoeken in winkellijst').fill('');

    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: 'Winkelen afgerond' }).click();
    await expect(page.getByText('Winkelen is afgerond. De winkellijst is leeggemaakt.')).toBeVisible();
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Winkelen afgerond' })).toBeDisabled();

    await expectNoConsoleErrors(consoleErrors);
  });
});
