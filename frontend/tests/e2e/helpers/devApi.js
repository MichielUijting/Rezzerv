const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEMO_HOUSEHOLD_ID = process.env.PLAYWRIGHT_HOUSEHOLD_ID || '0';
const SUPERUSER_EMAIL = process.env.PLAYWRIGHT_SUPERUSER_EMAIL || 'supergebruiker@rezzerv.local';
const SUPERUSER_PASSWORD = process.env.PLAYWRIGHT_SUPERUSER_PASSWORD || 'RezzervSuper123!';
const AUTHORIZATION_FIXTURE_MEMBER_EMAIL = 'lid@rezzerv.local';
const AUTHORIZATION_FIXTURE_MEMBER_ROLE = 'household.member';

async function parseJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function authenticateRequestSession(request) {
  const response = await request.post(`${API_URL}/api/auth/login`, {
    data: {
      email: SUPERUSER_EMAIL,
      password: SUPERUSER_PASSWORD,
    },
  });
  const payload = await parseJson(response);
  if (!response.ok()) {
    throw new Error(`API /api/auth/login failed with ${response.status()}: ${JSON.stringify(payload)}`);
  }
  return payload;
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

export async function resolveAuthorizedHouseholdId(request) {
  const household = await apiFetch(request, '/api/household');
  return String(household?.id || household?.household_id || DEMO_HOUSEHOLD_ID);
}

async function seedAuthorizationMembershipFixture(request, householdId) {
  const membersPayload = await apiFetch(
    request,
    `/api/households/${encodeURIComponent(householdId)}/authorization/members`,
  );
  const member = (membersPayload?.items || []).find(
    (item) => String(item?.email || '').trim().toLowerCase() === AUTHORIZATION_FIXTURE_MEMBER_EMAIL,
  );

  if (!member?.membership_id) {
    throw new Error(
      `Autorisatie-fixturelid ${AUTHORIZATION_FIXTURE_MEMBER_EMAIL} ontbreekt in huishouden ${householdId}.`,
    );
  }

  if (member.role_key !== AUTHORIZATION_FIXTURE_MEMBER_ROLE) {
    await apiFetch(
      request,
      `/api/households/${encodeURIComponent(householdId)}/authorization/members/${encodeURIComponent(member.membership_id)}/role`,
      {
        method: 'PUT',
        data: {
          role_key: AUTHORIZATION_FIXTURE_MEMBER_ROLE,
          reason: 'Deterministische browser-regressiefixture',
        },
      },
    );
  }
}

export async function cleanupRegressionFixtures(request) {
  return apiFetch(request, '/api/testing/fixtures/cleanup', { method: 'POST' });
}

export async function resetAndSeedStoreImportFixture(request) {
  await apiFetch(request, '/api/testing/fixtures/browser-regression/reset', { method: 'POST' });
  await apiFetch(request, '/api/testing/fixtures/receipts/seed-kassa', { method: 'POST' });

  const householdId = await resolveAuthorizedHouseholdId(request);
  await seedAuthorizationMembershipFixture(request, householdId);

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
  await page.getByLabel('E-mail').fill(SUPERUSER_EMAIL);
  await page.getByLabel('Wachtwoord').fill(SUPERUSER_PASSWORD);
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');
}

export { API_URL, DEMO_HOUSEHOLD_ID, SUPERUSER_EMAIL, SUPERUSER_PASSWORD };
