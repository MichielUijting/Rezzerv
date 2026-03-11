const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEMO_HOUSEHOLD_ID = 'demo-household';

async function parseJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function apiFetch(request, path, options = {}) {
  const response = await request.fetch(`${API_URL}${path}`, options);
  const payload = await parseJson(response);
  if (!response.ok()) {
    throw new Error(`API ${path} failed with ${response.status()}: ${JSON.stringify(payload)}`);
  }
  return payload;
}

export async function resetAndSeedStoreImportFixture(request) {
  await apiFetch(request, '/api/dev/reset-data', { method: 'POST' });
  await apiFetch(request, '/api/dev/generate-demo-data', { method: 'POST' });

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
        household_id: DEMO_HOUSEHOLD_ID,
        store_provider_code: providerCode,
      },
    });
  }

  const connections = await apiFetch(request, `/api/store-connections?householdId=${encodeURIComponent(DEMO_HOUSEHOLD_ID)}`);
  const lidlConnection = connections.find((item) => item.store_provider_code === 'lidl');
  if (!lidlConnection) {
    throw new Error('Lidl-koppeling ontbreekt na seed.');
  }

  await apiFetch(request, `/api/store-connections/${lidlConnection.id}/pull-purchases`, {
    method: 'POST',
    data: { mock_profile: 'default' },
  });

  return { providers, connections };
}

export async function loginThroughUi(page) {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill('admin@rezzerv.local');
  await page.getByLabel('Wachtwoord').fill('Rezzerv123');
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');
}

export { API_URL, DEMO_HOUSEHOLD_ID };
