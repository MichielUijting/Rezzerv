import { test as setup, expect } from '@playwright/test';
import {
  authenticateRequestSession,
  loginThroughUi,
  resetAndSeedStoreImportFixture,
} from './helpers/devApi';

const authFile = 'playwright/.auth/user.json';

setup('seed isolated household-0 fixtures and authenticate canonical superuser', async ({ page, request }) => {
  const session = await authenticateRequestSession(request);
  expect(String(session.active_household_id)).toBe('0');
  expect(String(session.role || '').toLowerCase()).toBe('owner');

  const seeded = await resetAndSeedStoreImportFixture(request);
  expect(String(seeded.householdId)).toBe('0');

  await loginThroughUi(page);
  await expect(page.getByText('Startpagina')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
