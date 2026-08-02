import { test as setup, expect } from '@playwright/test';
import {
  loginThroughUi,
  resetAndSeedStoreImportFixture,
  resolveAuthorizedHouseholdId,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed household-0 fixtures and authenticate documented test-admin', async ({ page, request }) => {
  const seeded = await resetAndSeedStoreImportFixture(request);
  expect(String(seeded.householdId)).toBe('0');

  await expect.poll(
    async () => resolveAuthorizedHouseholdId(request),
    { message: 'Playwright-API-autorisatie moet huishouden 0 gebruiken.' },
  ).toBe('0');

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
