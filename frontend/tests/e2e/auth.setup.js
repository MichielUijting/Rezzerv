import { test as setup, expect } from '@playwright/test';
import { loginThroughUi, resetAndSeedStoreImportFixture } from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';
const shouldSeedRegressionFixtures = process.env.PLAYWRIGHT_SKIP_FIXTURE_SEED !== '1';

setup('seed demo data and authenticate', async ({ page, request }) => {
  if (shouldSeedRegressionFixtures) {
    await resetAndSeedStoreImportFixture(request);
  }

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
