import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';
import { DEMO_HOUSEHOLD_ID } from './helpers/devApi.js';

test.describe('Instellingen Artikelgroepen frontend-regressie', () => {
  test('Universele artikelnaam blijft zichtbaar en bulktoewijzing wordt opgeslagen', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const universalArticleName = 'Mosterd fijne Dijon extra lange universele artikelnaam';
    let assignedGroupId = null;
    let assignmentPayload = null;

    const groups = [
      { id: 'group-sauzen', name: 'Sauzen' },
      { id: 'group-kruiden', name: 'Kruiden en smaakmakers' },
    ];

    await page.route('**/api/article-groups?household_id=*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, items: groups }),
      });
    });

    await page.route('**/api/article-groups/household-articles?household_id=*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [
            {
              id: 'household-article-mosterd',
              article_name: universalArticleName,
              article_group_id: assignedGroupId,
            },
          ],
        }),
      });
    });

    await page.route('**/api/households/*/articles/inventory-handling/batch', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          items: [
            {
              id: 'household-article-mosterd',
              default_inventory_handling: 'STOCK',
            },
          ],
        }),
      });
    });

    await page.route('**/api/household-articles/household-article-mosterd/article-group', async (route) => {
      assignmentPayload = JSON.parse(route.request().postData() || '{}');
      assignedGroupId = assignmentPayload.article_group_id || null;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          household_article_id: 'household-article-mosterd',
          article_group_id: assignedGroupId,
        }),
      });
    });

    await page.goto('/instellingen/artikelgroepen');

    await expect(page).toHaveURL(/\/instellingen\/artikelgroepen$/);
    const pageRoot = page.getByTestId('settings-article-groups-page');
    await expect(pageRoot).toBeVisible();
    await expect(page.getByText(universalArticleName, { exact: true })).toBeVisible();

    const filterFields = pageRoot.locator('input[placeholder="Filter"]');
    const articleFilter = filterFields.nth(1);
    await articleFilter.fill('dijon');
    await expect(page.getByText(universalArticleName, { exact: true })).toBeVisible();
    await articleFilter.fill('');

    const articleRow = pageRoot.locator('tbody tr').filter({
      hasText: universalArticleName,
    });
    await articleRow.locator('input[type="checkbox"]').first().check();
    await page.getByRole('button', {
      name: 'Toewijzen aan Artikelgroep',
      exact: true,
    }).click();

    const assignDialog = page.getByRole('dialog').filter({
      hasText: 'Toewijzen aan Artikelgroep',
    });
    await expect(assignDialog).toBeVisible();
    await assignDialog.locator('select').selectOption('group-sauzen');
    await assignDialog.getByRole('button', {
      name: 'Opslaan',
      exact: true,
    }).click();

    await expect.poll(() => assignmentPayload).toEqual({
      household_id: String(DEMO_HOUSEHOLD_ID),
      article_group_id: 'group-sauzen',
    });
    await expect(page.getByText('Geselecteerde huishoudartikelen bijgewerkt.', {
      exact: true,
    })).toBeVisible();
    await expect(articleRow.locator('select')).toHaveValue('group-sauzen');

    await expectNoConsoleErrors(consoleErrors);
  });
});
