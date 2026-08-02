const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEMO_HOUSEHOLD_ID = process.env.PLAYWRIGHT_HOUSEHOLD_ID || '0';
const TEST_ADMIN_EMAIL = process.env.PLAYWRIGHT_TEST_ADMIN_EMAIL || 'test-admin@rezzerv.local';
const TEST_ADMIN_PASSWORD = process.env.PLAYWRIGHT_TEST_ADMIN_PASSWORD;

function requireCredential(value, name) {
  if (!value) {
    throw new Error(`${name} ontbreekt in de Playwright-omgeving.`);
  }
  return value;
}

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
  const response = await request.fetch(`${API_URL}${path}`, {
    ...options,
    headers: { ...(options.headers || {}) },
  });
  const payload = await parseJson(response);

  if (!response.ok()) {
    throw new Error(`API ${path} failed with ${response.status()}: ${JSON.stringify(payload)}`);
  }

  return payload;
}

export async function authenticateTestAdminRequestSession(request) {
  const response = await request.post(`${API_URL}/api/auth/login`, {
    data: {
      email: TEST_ADMIN_EMAIL,
      password: requireCredential(TEST_ADMIN_PASSWORD, 'test-admin wachtwoord'),
    },
  });
  const payload = await parseJson(response);
  if (!response.ok()) {
    throw new Error(
      `API /api/auth/login (test-admin) failed with ${response.status()}: ${JSON.stringify(payload)}`,
    );
  }
  if (String(payload?.active_household_id ?? '') !== String(DEMO_HOUSEHOLD_ID)) {
    throw new Error(
      `Playwright moet huishouden ${DEMO_HOUSEHOLD_ID} gebruiken, ontvangen ${payload?.active_household_id}.`,
    );
  }
  if (String(payload?.role || '').toLowerCase() !== 'owner') {
    throw new Error(`Test-admin heeft niet de verwachte owner-context: ${JSON.stringify(payload)}`);
  }
  return payload;
}

export async function resolveAuthorizedHouseholdId(request) {
  const household = await apiFetch(request, '/api/household');
  const resolvedHouseholdId = String(
    household?.active_household_id
      || household?.id
      || household?.household_id
      || DEMO_HOUSEHOLD_ID
  );
  if (resolvedHouseholdId !== String(DEMO_HOUSEHOLD_ID)) {
    throw new Error(
      `Playwright moet huishouden ${DEMO_HOUSEHOLD_ID} gebruiken, maar ontving ${resolvedHouseholdId}.`,
    );
  }
  return resolvedHouseholdId;
}

export async function resetAndSeedStoreImportFixture(request) {
  await authenticateTestAdminRequestSession(request);
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

  const connections = await apiFetch(
    request,
    `/api/store-connections?householdId=${encodeURIComponent(householdId)}`,
  );
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
  await page.getByLabel('E-mail').fill(TEST_ADMIN_EMAIL);
  await page.getByLabel('Wachtwoord').fill(requireCredential(TEST_ADMIN_PASSWORD, 'test-admin wachtwoord'));
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');
}

export {
  API_URL,
  DEMO_HOUSEHOLD_ID,
  TEST_ADMIN_EMAIL,
  TEST_ADMIN_PASSWORD,
};
