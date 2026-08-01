import { test as setup, expect } from '@playwright/test';
import {
  authenticateRequestSession,
  loginThroughUi,
  resetAndSeedStoreImportFixture,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed demo data and authenticate', async ({ page, request }) => {
  await authenticateRequestSession(request);
  await resetAndSeedStoreImportFixture(request);
  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
