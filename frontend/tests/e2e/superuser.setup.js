import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/superuser.json';
const SUPERUSER_EMAIL = process.env.REZZERV_TEST_SUPERUSER_EMAIL || 'supergebruiker@rezzerv.local';
const SUPERUSER_PASSWORD = process.env.REZZERV_TEST_SUPERUSER_PASSWORD;

function requireCredential(value, name) {
  if (!value) throw new Error(`${name} ontbreekt in de Playwright-omgeving.`);
  return value;
}

setup('authenticate documented Superuser for platform-functional regressions', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(SUPERUSER_EMAIL);
  await page.getByTestId('login-password').fill(requireCredential(SUPERUSER_PASSWORD, 'Superuser wachtwoord'));
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');

  const session = await page.evaluate(async () => {
    const response = await fetch('/api/session', { credentials: 'include' });
    return { status: response.status, payload: await response.json() };
  });

  expect(session.status).toBe(200);
  expect(session.payload?.is_platform_superuser).toBe(true);
  expect(session.payload?.permissions?.['platform.external_products.view']).toBe(true);
  expect(session.payload?.permissions?.['platform.external_products.search']).toBe(true);
  expect(session.payload?.permissions?.['platform.external_products.link_existing']).toBe(true);

  await page.context().storageState({ path: authFile });
});
