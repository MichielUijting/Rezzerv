import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

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
    await expect(page.getByTestId('settings-article-groups-page')).toBeVisible();
    await expect(page.getByText(universalArticleName, { exact: true })).toBeVisible();

    await page.getByLabel('Filter op artikel', { exact: true }).fill('dijon');
    await expect(page.getByText(universalArticleName, { exact: true })).toBeVisible();
    await page.getByLabel('Filter op artikel', { exact: true }).fill('');

    await page.getByLabel(`Selecteer ${universalArticleName}`, { exact: true }).check();
    await page.getByRole('button', { name: 'Toewijzen aan artikelgroep', exact: true }).click();

    const assignDialog = page.getByRole('dialog', { name: 'Toewijzen aan artikelgroep' });
    await expect(assignDialog).toBeVisible();
    await assignDialog.locator('select').selectOption('group-sauzen');
    await assignDialog.getByRole('button', { name: 'Toewijzen', exact: true }).click();

    const confirmDialog = page.getByRole('dialog', { name: 'Bevestiging' });
    await expect(confirmDialog).toContainText('Sauzen');
    await confirmDialog.getByRole('button', { name: 'Opslaan', exact: true }).click();

    await expect.poll(() => assignmentPayload).toEqual({
      household_id: '1',
      article_group_id: 'group-sauzen',
    });
    await expect(page.getByText(/1 voorraadartikel toegewezen aan Artikelgroep Sauzen\./)).toBeVisible();
    await expect(page.getByLabel(`Artikelgroep ${universalArticleName}`, { exact: true })).toHaveValue('group-sauzen');

    await expectNoConsoleErrors(consoleErrors);
  });
});
