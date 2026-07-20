import { test as setup, expect } from '@playwright/test';
import {
  loginThroughUi,
  resetAndSeedStoreImportFixture,
  resolveAuthorizedHouseholdId,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed demo data and authenticate', async ({ page, request }) => {
  await resetAndSeedStoreImportFixture(request);
  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await expect.poll(
    async () => resolveAuthorizedHouseholdId(request),
    { message: 'Playwright-autorisatie moet huishouden 0 gebruiken.' },
  ).toBe('0');
  await page.context().storageState({ path: authFile });
});
