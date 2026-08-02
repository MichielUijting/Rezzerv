import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';


test.describe('Winkelen Release 1 frontend-regressie', () => {
  test('echte gecombineerde artikelzoekroute levert resultaten zonder API-fout', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);

    await page.goto('/winkelen');
    await expect(page).toHaveURL(/\/winkelen$/);
    await expect(page.getByLabel('Zoeken in', { exact: true })).toHaveCount(0);
    await page.getByLabel('Artikel zoeken').fill('Regressie-artikel');

    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Regressie-artikel');
    await expect(page.getByLabel('Zoekresultaten samenvatting')).toHaveCount(0);
    await expectNoConsoleErrors(consoleErrors);
  });

  test('gecombineerd zoeken, toevoegen, vaste tabelbreedte, omvang, filteren, afvinken en afronden', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    let activeListId = 'shopping-list-active-1';
    let items = [];

    const candidates = [
      {
        source_type: 'household_article',
        source_id: 'household-article-melk',
        label: 'Melk',
        article_name: 'Melk',
        article_group_name: 'Zuivel',
        product_type_name: 'Halfvolle melk',
      },
      {
        source_type: 'product_type',
        source_id: 'product-type-melk',
        label: 'Melkproduct met een uitzonderlijk lange producttypenaam die de tabel niet mag verbreden',
        article_name: 'Melkproduct met een uitzonderlijk lange producttypenaam die de tabel niet mag verbreden',
        article_group_name: '',
        product_type_name: 'Melkproduct met een uitzonderlijk lange producttypenaam die de tabel niet mag verbreden',
      },
      {
        source_type: 'article_group',
        source_id: 'article-group-zuivel',
        label: 'Melk en zuivel',
        article_name: 'Melk en zuivel',
        article_group_name: 'Melk en zuivel',
        product_type_name: '',
      },
    ];

    await page.route('**/api/shopping-list/catalog-search?*', async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get('scope')).toBe('all');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          scope: 'all',
          query: url.searchParams.get('query'),
          items: candidates,
          total: candidates.length,
          counts: { household_article: 1, product_type: 1, article_group: 1 },
        }),
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
        size: '',
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
    await expect(page.getByLabel('Zoeken in', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('Catalogus zoeken')).toHaveCount(0);
    await expect(page.getByLabel('Artikel zoeken')).toBeVisible();
    await expect(page.getByLabel('Zoekresultaten samenvatting')).toHaveCount(0);

    const sortableHeaders = [
      page.getByRole('columnheader', { name: 'Sorteer op Artikel', exact: true }),
      page.getByRole('columnheader', { name: 'Sorteer op Artikelgroep', exact: true }),
      page.getByRole('columnheader', { name: 'Sorteer op Producttype', exact: true }),
      page.getByRole('columnheader', { name: 'Sorteer op Omvang', exact: true }),
    ];
    const sortIndicator = (header) => header.locator('span').filter({ hasText: /^[\^v]$/ });

    await expect(sortableHeaders[0]).toHaveAttribute('aria-sort', /ascending|descending/);
    await expect(sortIndicator(sortableHeaders[0])).toHaveCount(1);
    for (let index = 1; index < sortableHeaders.length; index += 1) {
      await expect(sortableHeaders[index]).toHaveAttribute('aria-sort', 'none');
      await expect(sortIndicator(sortableHeaders[index])).toHaveCount(0);
    }

    for (let index = 1; index < sortableHeaders.length; index += 1) {
      await sortableHeaders[index].click();
      await expect(sortableHeaders[index]).toHaveAttribute('aria-sort', /ascending|descending/);
      await expect(sortIndicator(sortableHeaders[index])).toHaveCount(1);
      for (let otherIndex = 0; otherIndex < sortableHeaders.length; otherIndex += 1) {
        if (otherIndex === index) continue;
        await expect(sortableHeaders[otherIndex]).toHaveAttribute('aria-sort', 'none');
        await expect(sortIndicator(sortableHeaders[otherIndex])).toHaveCount(0);
      }
    }

    await expect(page.getByRole('columnheader', { name: /Aantal/ })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: /Volume/ })).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: /Eenheid/ })).toHaveCount(0);

    const filterInputs = page.locator('thead tr:nth-child(2) .rz-input');
    await expect(filterInputs).toHaveCount(4);
    for (let index = 0; index < await filterInputs.count(); index += 1) {
      const colors = await filterInputs.nth(index).evaluate((element) => {
        const style = window.getComputedStyle(element);
        return { color: style.color, backgroundColor: style.backgroundColor };
      });
      expect(colors.color).not.toBe(colors.backgroundColor);
      expect(colors.color).not.toBe('rgba(0, 0, 0, 0)');
      await expect(filterInputs.nth(index)).not.toHaveValue(/[\^v]/);
    }

    const articleSearchBox = await page.getByLabel('Artikel zoeken').boundingBox();
    const resultBox = await page.getByLabel('Zoekresultaat').boundingBox();
    const addButtonBox = await page.getByRole('button', { name: 'Toevoegen' }).boundingBox();
    expect(articleSearchBox).not.toBeNull();
    expect(resultBox).not.toBeNull();
    expect(addButtonBox).not.toBeNull();
    expect(Math.abs((articleSearchBox.y + articleSearchBox.height) - (addButtonBox.y + addButtonBox.height))).toBeLessThanOrEqual(2);
    expect(Math.abs((resultBox.y + resultBox.height) - (addButtonBox.y + addButtonBox.height))).toBeLessThanOrEqual(2);

    const table = page.getByTestId('shopping-list-table');
    await expect(table).toHaveClass(/rz-table--resizable-columns/);
    const widthBeforeSearch = await table.evaluate((element) => Math.round(element.getBoundingClientRect().width));
    const tableTopBeforeSearch = await table.evaluate((element) => Math.round(element.getBoundingClientRect().top));

    await page.getByLabel('Artikel zoeken').fill('melk');
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Melk — Huishoudartikel');
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Producttype');
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Artikelgroep');
    await expect(page.getByLabel('Zoekresultaten samenvatting')).toHaveCount(0);

    const widthAfterSearch = await table.evaluate((element) => Math.round(element.getBoundingClientRect().width));
    const tableTopAfterSearch = await table.evaluate((element) => Math.round(element.getBoundingClientRect().top));
    expect(widthAfterSearch).toBe(widthBeforeSearch);
    expect(tableTopAfterSearch).toBe(tableTopBeforeSearch);

    await page.getByLabel('Zoekresultaat').selectOption('household_article:household-article-melk');
    await page.getByRole('button', { name: 'Toevoegen' }).click();

    await expect(page.getByText('Melk', { exact: true })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Zuivel', exact: true })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Halfvolle melk', exact: true })).toBeVisible();
    const widthAfterAdd = await table.evaluate((element) => Math.round(element.getBoundingClientRect().width));
    expect(widthAfterAdd).toBe(widthBeforeSearch);

    await page.getByLabel('Omvang Melk').fill('2 × 1,5 liter');
    await page.getByLabel('Omvang Melk').blur();
    await page.getByLabel('Opmerking Melk').fill('Halfvol');
    await page.getByLabel('Opmerking Melk').blur();

    await page.getByLabel('Gekocht Melk').check();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();
    await page.reload();
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();
    await expect(page.getByLabel('Omvang Melk')).toHaveValue('2 × 1,5 liter');
    await expect(page.getByLabel('Opmerking Melk')).toHaveValue('Halfvol');
    await expect(page.getByLabel('Aantal Melk')).toHaveCount(0);
    await expect(page.getByLabel('Volume Melk')).toHaveCount(0);
    await expect(page.getByLabel('Eenheid Melk')).toHaveCount(0);

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
