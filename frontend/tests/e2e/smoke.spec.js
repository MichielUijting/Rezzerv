import { test, expect } from '@playwright/test';

function attachConsoleErrorCollector(page) {
  const consoleErrors = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    consoleErrors.push(error.message);
  });
  return consoleErrors;
}

test('authenticated user can open key screens without console errors', async ({ page }) => {
  const consoleErrors = attachConsoleErrorCollector(page);

  await page.goto('/home');
  await expect(page.getByText('Startpagina')).toBeVisible();

  await page.goto('/winkels');
  await expect(page.getByText('Winkelkoppelingen')).toBeVisible();

  await page.goto('/voorraad');
  await expect(page.getByText('Voorraad')).toBeVisible();

  expect(consoleErrors).toEqual([]);
});
