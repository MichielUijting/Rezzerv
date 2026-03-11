import { test, expect } from '@playwright/test';

test.describe('Winkels scherm smoke', () => {
  test('shows connected stores and restores the latest open batch', async ({ page }) => {
    await page.goto('/winkels');

    await expect(page.getByTestId('store-import-simplification-banner')).toContainText('Vereenvoudigingsniveau winkelimport');
    await expect(page.getByTestId('connected-stores-section')).toBeVisible();

    await expect(page.getByTestId('store-provider-lidl')).toContainText('Lidl');
    await expect(page.getByTestId('store-provider-jumbo')).toContainText('Jumbo');

    await expect(page.getByTestId('pull-purchases-lidl')).toBeVisible();
    await expect(page.getByTestId('pull-purchases-jumbo')).toBeVisible();

    await expect(page.getByTestId('active-batch-card')).toBeVisible();
    await expect(page.getByTestId('active-batch-title')).toContainText('Kassabon Lidl');
    await expect(page.getByTestId('process-active-batch')).toBeVisible();
  });

  test('can pull purchases for another connected store', async ({ page }) => {
    await page.goto('/winkels');

    await page.getByTestId('pull-purchases-jumbo').click();

    await expect(page.getByTestId('active-batch-card')).toBeVisible();
    await expect(page.getByTestId('active-batch-title')).toContainText('Kassabon Jumbo');
  });
});
