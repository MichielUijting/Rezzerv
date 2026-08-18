import { readFile } from 'node:fs/promises';
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
    await page.getByLabel('Artikel toevoegen').fill('Regressie-artikel');

    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.getByLabel('Zoekresultaat')).toContainText('Regressie-artikel');
    await expectNoConsoleErrors(consoleErrors);
  });

  test('nieuwe tabelindeling, bulkselectie, export, verwijderen en afronden', async ({ page }) => {
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
        source_id: 'product-type-pasta',
        label: 'Pasta',
        article_name: 'Pasta',
        article_group_name: 'Houdbaar',
        product_type_name: 'Gebruiksklaar',
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
          counts: { household_article: 1, product_type: 1, article_group: 0 },
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
      const itemId = decodeURIComponent(route.request().url().split('/').pop());
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
      return route.fallback();
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
    const shoppingPage = page.getByTestId('shopping-page');
    const table = page.getByTestId('shopping-list-table');

    await expect(shoppingPage).toBeVisible();
    await expect(shoppingPage.getByRole('heading', { name: 'Winkelen — 0 artikelen' })).toBeVisible();
    await expect(page.getByText('Artikel toevoegen', { exact: true })).toBeVisible();
    await expect(page.getByText('Zoek tegelijk in Huishoudartikelen')).toHaveCount(0);
    await expect(page.getByRole('columnheader', { name: /Artikelgroep/ })).toHaveCount(0);
    await expect(table.locator('thead tr:first-child th').first()).toBeVisible();

    const headerLabels = await table.locator('thead tr:first-child th').allTextContents();
    expect(headerLabels.map((value) => value.replace(/\s*[\^v]\s*$/, '').trim())).toEqual(['', 'Artikel', 'Producttype', 'Omvang', 'Opmerking', 'Gekocht']);

    await expect(table.locator('thead tr:first-child')).toHaveClass(/rz-table-header/);
    const headerColor = await table.getByRole('button', { name: 'Artikel sorteren', exact: true }).evaluate(
      (element) => window.getComputedStyle(element).color,
    );
    expect(headerColor).toBe('rgb(255, 255, 255)');

    const sortableHeaders = ['Artikel', 'Producttype', 'Omvang', 'Opmerking', 'Gekocht'].map((label) => ({
      label,
      button: table.getByRole('button', { name: `${label} sorteren`, exact: true }),
      header: table.getByRole('columnheader', { name: `${label} sorteren`, exact: true }),
    }));

    await expect(sortableHeaders[0].header).toHaveAttribute('aria-sort', 'ascending');
    for (const { header } of sortableHeaders.slice(1)) {
      await expect(header).toHaveAttribute('aria-sort', 'none');
    }

    for (const { button, header } of sortableHeaders.slice(1)) {
      await button.click();
      await expect(header).toHaveAttribute('aria-sort', 'ascending');
      await expect(header.locator('.rz-sort-indicator')).toHaveClass(/is-active/);
    }

    await expect(page.getByLabel('Filter gekocht')).toHaveAttribute('type', 'checkbox');
    const filterControls = table.locator('thead tr:nth-child(2) .rz-input');
    await expect(filterControls).toHaveCount(2);
    for (let index = 0; index < await filterControls.count(); index += 1) {
      const metrics = await filterControls.nth(index).evaluate((element) => {
        const style = window.getComputedStyle(element);
        const numericLineHeight = Number.parseFloat(style.lineHeight);
        const fallbackLineHeight = Number.parseFloat(style.fontSize) * 1.2;
        return {
          height: element.getBoundingClientRect().height,
          minHeight: style.minHeight,
          color: style.color,
          backgroundColor: style.backgroundColor,
          effectiveLineHeight: Number.isFinite(numericLineHeight) ? numericLineHeight : fallbackLineHeight,
        };
      });
      expect(metrics.minHeight).toBe('20px');
      expect(metrics.height).toBeGreaterThanOrEqual(20);
      expect(metrics.height).toBeLessThan(30);
      expect(metrics.color).not.toBe(metrics.backgroundColor);
      expect(metrics.effectiveLineHeight).toBeLessThan(metrics.height);
    }
    const filterRowHeight = await table.locator('thead tr:nth-child(2)').evaluate((element) => element.getBoundingClientRect().height);
    expect(filterRowHeight).toBeGreaterThanOrEqual(34);

    const columnWidths = await table.locator('colgroup col').evaluateAll((columns) => columns.map((column) => Number.parseFloat(column.style.width)));
    expect(columnWidths).toEqual([60, 330, 300, 120, 220, 90]);

    const resizeHandles = table.getByRole('separator', { name: 'Kolom breedte aanpassen' });
    await expect(resizeHandles).toHaveCount(6);
    const articleResizeHandle = resizeHandles.nth(1);
    const resizeBox = await articleResizeHandle.boundingBox();
    if (!resizeBox) throw new Error('Resize-handle voor Artikel ontbreekt.');
    const articleWidthBefore = Number.parseFloat(await table.locator('colgroup col').nth(1).evaluate((column) => column.style.width));
    await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(resizeBox.x + resizeBox.width / 2 + 60, resizeBox.y + resizeBox.height / 2);
    await page.mouse.up();
    const articleWidthAfter = Number.parseFloat(await table.locator('colgroup col').nth(1).evaluate((column) => column.style.width));
    expect(articleWidthAfter).toBeGreaterThan(articleWidthBefore + 40);

    const articleSearchBox = await page.getByLabel('Artikel toevoegen').boundingBox();
    const resultBox = await page.getByLabel('Zoekresultaat').boundingBox();
    const addButtonBox = await page.getByRole('button', { name: 'Toevoegen' }).boundingBox();
    expect(Math.abs((articleSearchBox.y + articleSearchBox.height) - (addButtonBox.y + addButtonBox.height))).toBeLessThanOrEqual(2);
    expect(Math.abs((resultBox.y + resultBox.height) - (addButtonBox.y + addButtonBox.height))).toBeLessThanOrEqual(2);

    await page.getByLabel('Artikel toevoegen').fill('melk');
    await page.getByLabel('Zoekresultaat').selectOption('household_article:household-article-melk');
    await page.getByRole('button', { name: 'Toevoegen' }).click();
    await expect(page.getByRole('heading', { name: 'Winkelen — 1 artikelen' })).toBeVisible();
    await expect(page.getByRole('cell', { name: 'Zuivel', exact: true })).toHaveCount(0);
    await expect(page.getByRole('cell', { name: 'Halfvolle melk', exact: true })).toBeVisible();

    await page.getByLabel('Omvang Melk').fill('2 × 1,5 liter');
    await page.getByLabel('Omvang Melk').blur();
    await page.getByLabel('Opmerking Melk').fill('Halfvol');
    await page.getByLabel('Opmerking Melk').blur();
    await page.getByLabel('Gekocht Melk').check();
    await page.reload();
    await expect(page.getByLabel('Omvang Melk')).toHaveValue('2 × 1,5 liter');
    await expect(page.getByLabel('Opmerking Melk')).toHaveValue('Halfvol');
    await expect(page.getByLabel('Gekocht Melk')).toBeChecked();

    await expect(shoppingPage.getByRole('button', { name: 'Verwijderen' })).toBeDisabled();
    await expect(shoppingPage.getByRole('button', { name: 'Exporteren' })).toBeDisabled();
    await expect(shoppingPage.getByRole('button', { name: 'Winkelen afgerond' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Winkelen afgerond' })).toBeVisible();
    await expect(shoppingPage.getByRole('button', { name: 'Verwijderen' }).locator('svg')).toHaveCount(0);
    await expect(shoppingPage.getByRole('button', { name: 'Exporteren' }).locator('svg')).toHaveCount(0);

    await page.getByLabel('Selecteer Melk').check();
    await expect(shoppingPage.getByRole('button', { name: 'Verwijderen' })).toBeEnabled();
    await expect(shoppingPage.getByRole('button', { name: 'Exporteren' })).toBeEnabled();

    const exportDownloadPromise = page.waitForEvent('download');
    await shoppingPage.getByRole('button', { name: 'Exporteren' }).click();
    const exportDownload = await exportDownloadPromise;
    expect(exportDownload.suggestedFilename()).toBe('winkelen-geselecteerde-rijen.csv');
    const exportedCsv = await readFile(await exportDownload.path(), 'utf8');
    expect(exportedCsv).toContain('"Artikel";"Producttype";"Omvang";"Opmerking";"Gekocht"');
    expect(exportedCsv).toContain('"Melk";"Halfvolle melk";"2 × 1,5 liter";"Halfvol";"Ja"');

    const nativeDialogs = [];
    page.on('dialog', async (dialog) => {
      nativeDialogs.push(dialog.message());
      await dialog.dismiss();
    });

    await shoppingPage.getByRole('button', { name: 'Verwijderen' }).click();
    const deleteDialog = page.getByTestId('shopping-delete-confirmation');
    await expect(deleteDialog).toBeVisible();
    await expect(deleteDialog.getByText('1 geselecteerde rij verwijderen?', { exact: true })).toBeVisible();
    await page.getByTestId('shopping-delete-confirmation-secondary-button').click();
    await expect(page.getByLabel('Selecteer Melk')).toBeChecked();

    await shoppingPage.getByRole('button', { name: 'Verwijderen' }).click();
    await page.getByTestId('shopping-delete-confirmation-primary-button').click();
    await expect(page.getByRole('heading', { name: 'Winkelen — 0 artikelen' })).toBeVisible();
    await expect(page.getByLabel('Selecteer Melk')).toHaveCount(0);

    await page.getByLabel('Artikel toevoegen').fill('pasta');
    await page.getByLabel('Zoekresultaat').selectOption('product_type:product-type-pasta');
    await page.getByRole('button', { name: 'Toevoegen' }).click();

    await page.getByRole('button', { name: 'Winkelen afgerond' }).click();
    const completeDialog = page.getByTestId('shopping-complete-confirmation');
    await expect(completeDialog).toBeVisible();
    await expect(completeDialog.getByText('Voorraad en bronlijsten blijven ongewijzigd.', { exact: true })).toBeVisible();
    await page.getByTestId('shopping-complete-confirmation-primary-button').click();
    await expect(page.getByText('Winkelen is afgerond. De winkellijst is leeggemaakt.')).toBeVisible();
    expect(nativeDialogs).toEqual([]);
    await expect(page.getByText('Nog geen artikelen op de winkellijst.')).toBeVisible();

    await expectNoConsoleErrors(consoleErrors);
  });
});
