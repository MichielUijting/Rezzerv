const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEMO_HOUSEHOLD_ID = process.env.PLAYWRIGHT_HOUSEHOLD_ID || '1';
const DEV_ADMIN_TOKEN = process.env.PLAYWRIGHT_ADMIN_TOKEN || 'rezzerv-dev-token::admin@rezzerv.local';

async function parseJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function apiFetch(request, path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    Authorization: `Bearer ${DEV_ADMIN_TOKEN}`,
  };

  const response = await request.fetch(`${API_URL}${path}`, { ...options, headers });
  const payload = await parseJson(response);

  if (!response.ok()) {
    throw new Error(`API ${path} failed with ${response.status()}: ${JSON.stringify(payload)}`);
  }

  return payload;
}

export async function resolveAuthorizedHouseholdId(request) {
  const household = await apiFetch(request, '/api/household');
  return String(household?.id || household?.household_id || DEMO_HOUSEHOLD_ID);
}

export async function cleanupRegressionFixtures(request) {
  return apiFetch(request, '/api/testing/fixtures/cleanup', { method: 'POST' });
}

export async function resetAndSeedStoreImportFixture(request) {
  await apiFetch(request, '/api/testing/fixtures/browser-regression/reset', { method: 'POST' });
  await apiFetch(request, '/api/testing/fixtures/receipts/seed-kassa', { method: 'POST' });

  const householdId = await resolveAuthorizedHouseholdId(request);
  const providers = await apiFetch(request, '/api/store-providers');
  const requiredProviderCodes = ['lidl', 'jumbo'];

  for (const providerCode of requiredProviderCodes) {
    const provider = providers.find((item) => item.code === providerCode);
    if (!provider) {
      throw new Error(`Store provider ${providerCode} ontbreekt in de testomgeving.`);
    }

    await apiFetch(request, '/api/store-connections', {
      method: 'POST',
      data: {
        household_id: householdId,
        store_provider_code: providerCode,
      },
    });
  }

  const connections = await apiFetch(request, `/api/store-connections?householdId=${encodeURIComponent(householdId)}`);
  const lidlConnection = connections.find((item) => item.store_provider_code === 'lidl');

  if (!lidlConnection) {
    throw new Error('Lidl-koppeling ontbreekt na seed.');
  }

  await apiFetch(request, `/api/store-connections/${lidlConnection.id}/pull-purchases`, {
    method: 'POST',
    data: { mock_profile: 'default' },
  });

  return { householdId, providers, connections };
}

export async function loginThroughUi(page) {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill('admin@rezzerv.local');
  await page.getByLabel('Wachtwoord').fill('Rezzerv123');
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');
}

export { API_URL, DEMO_HOUSEHOLD_ID };
