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

  const browserSessionContext = await page.evaluate(async () => {
    async function fetchJson(path) {
      const response = await fetch(path, { credentials: 'include' });
      const text = await response.text();
      let payload = null;
      try {
        payload = text ? JSON.parse(text) : null;
      } catch {
        payload = text;
      }
      return { path, status: response.status, payload };
    }

    const [session, household] = await Promise.all([
      fetchJson('/api/session'),
      fetchJson('/api/household'),
    ]);

    return { session, household };
  });

  console.log(`BROWSER_SESSION_CONTEXT=${JSON.stringify(browserSessionContext)}`);

  expect(browserSessionContext.session.status).toBe(200);
  expect(browserSessionContext.household.status).toBe(200);
  expect(String(browserSessionContext.session.payload?.active_household_id ?? '')).toBe('0');
  expect(String(
    browserSessionContext.household.payload?.active_household_id
      ?? browserSessionContext.household.payload?.id
      ?? browserSessionContext.household.payload?.household_id
      ?? ''
  )).toBe('0');

  await page.context().storageState({ path: authFile });
});
