import { test as setup, expect } from '@playwright/test';
import { loginThroughUi, resetAndSeedStoreImportFixture } from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';
const shouldSeedRegressionFixtures = process.env.PLAYWRIGHT_SKIP_FIXTURE_SEED !== '1';
const persistedSessionKeys = [
  'rezzerv_token',
  'rezzerv_user_email',
  'rezzerv_household_name',
  'rezzerv_auth_context',
];

setup('seed demo data and authenticate', async ({ page, request }) => {
  if (shouldSeedRegressionFixtures) {
    await resetAndSeedStoreImportFixture(request);
  }

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();

  // Playwright storageState bewaart geen sessionStorage. Kopieer uitsluitend de
  // authentisatiesleutels naar de bestaande legacy-opslag, zodat authSession.js
  // ze per nieuw tabblad eenmalig naar sessionStorage migreert en daarna wist.
  await page.evaluate((keys) => {
    for (const key of keys) {
      const value = sessionStorage.getItem(key);
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    }
  }, persistedSessionKeys);

  await page.context().storageState({ path: authFile });
});
