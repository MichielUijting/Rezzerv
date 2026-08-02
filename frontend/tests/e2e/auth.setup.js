import { test as setup, expect } from '@playwright/test';
import {
  authenticateOwnerRequestSession,
  loginThroughUi,
  resetAndSeedStoreImportFixture,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed isolated household-1 fixtures and authenticate role-based owner', async ({ page, request }) => {
  const seeded = await resetAndSeedStoreImportFixture(request);
  expect(String(seeded.householdId)).toBe('1');

  const ownerSession = await authenticateOwnerRequestSession(request);
  expect(String(ownerSession.active_household_id)).toBe('1');
  expect(String(ownerSession.role || '').toLowerCase()).toBe('owner');

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
