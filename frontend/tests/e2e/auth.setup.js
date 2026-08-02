import { test as setup, expect } from '@playwright/test';
import {
  authenticateTestAdminRequestSession,
  loginThroughUi,
  resetAndSeedStoreImportFixture,
  resolveAuthorizedHouseholdId,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed household-0 fixtures and authenticate documented test-admin', async ({ page, request }) => {
  const session = await authenticateTestAdminRequestSession(request);
  expect(String(session.active_household_id)).toBe('0');
  expect(String(session.role || '').toLowerCase()).toBe('owner');

  const seeded = await resetAndSeedStoreImportFixture(request);
  expect(String(seeded.householdId)).toBe('0');

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await expect.poll(
    async () => resolveAuthorizedHouseholdId(request),
    { message: 'Playwright-autorisatie moet huishouden 0 gebruiken.' },
  ).toBe('0');
  await page.context().storageState({ path: authFile });
});
