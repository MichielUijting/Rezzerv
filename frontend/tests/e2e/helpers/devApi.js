const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEMO_HOUSEHOLD_ID = process.env.PLAYWRIGHT_HOUSEHOLD_ID || '1';
const PLATFORM_EMAIL = process.env.PLAYWRIGHT_PLATFORM_EMAIL || 'supergebruiker@rezzerv.local';
const PLATFORM_PASSWORD = process.env.PLAYWRIGHT_PLATFORM_PASSWORD;
const OWNER_EMAIL = process.env.PLAYWRIGHT_OWNER_EMAIL || 'regressie-eigenaar@rezzerv.local';
const OWNER_PASSWORD = process.env.PLAYWRIGHT_OWNER_PASSWORD;
const AUTHORIZATION_FIXTURE_MEMBER_EMAIL = process.env.PLAYWRIGHT_MEMBER_EMAIL || 'regressie-lid@rezzerv.local';
const AUTHORIZATION_FIXTURE_MEMBER_ROLE = 'household.member';

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

async function authenticateRequestAs(request, email, password, label) {
  const response = await request.post(`${API_URL}/api/auth/login`, {
    data: {
      email: requireCredential(email, `${label} e-mail`),
      password: requireCredential(password, `${label} wachtwoord`),
    },
  });
  const payload = await parseJson(response);
  if (!response.ok()) {
    throw new Error(`API /api/auth/login (${label}) failed with ${response.status()}: ${JSON.stringify(payload)}`);
  }
  return payload;
}

export async function authenticatePlatformRequestSession(request) {
  const payload = await authenticateRequestAs(
    request,
    PLATFORM_EMAIL,
    PLATFORM_PASSWORD,
    'platform-superuser',
  );
  if (String(payload?.active_household_id ?? '') !== '0') {
    throw new Error(`Platform-superuser heeft niet huishouden 0: ${JSON.stringify(payload)}`);
  }
  return payload;
}

export async function authenticateOwnerRequestSession(request) {
  const payload = await authenticateRequestAs(
    request,
    OWNER_EMAIL,
    OWNER_PASSWORD,
    'regressie-eigenaar',
  );
  if (String(payload?.active_household_id ?? '') !== String(DEMO_HOUSEHOLD_ID)) {
    throw new Error(
      `Verkeerd actief regressiehuishouden: verwacht ${DEMO_HOUSEHOLD_ID}, ontvangen ${payload?.active_household_id}.`,
    );
  }
  if (String(payload?.role || '').toLowerCase() !== 'owner') {
    throw new Error(`Regressie-eigenaar heeft verkeerde rol: ${JSON.stringify(payload)}`);
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

async function verifyAuthorizationMembershipFixture(request, householdId) {
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
    throw new Error(
      `Autorisatie-fixturelid heeft rol ${member.role_key}; verwacht ${AUTHORIZATION_FIXTURE_MEMBER_ROLE}.`,
    );
  }
}

export async function resetAndSeedStoreImportFixture(request) {
  await authenticatePlatformRequestSession(request);
  await apiFetch(request, '/api/testing/fixtures/browser-regression/reset', { method: 'POST' });
  await apiFetch(request, '/api/testing/fixtures/receipts/seed-kassa', { method: 'POST' });

  await authenticateOwnerRequestSession(request);
  const householdId = await resolveAuthorizedHouseholdId(request);
  if (householdId !== String(DEMO_HOUSEHOLD_ID)) {
    throw new Error(`Verkeerd actief regressiehuishouden: verwacht ${DEMO_HOUSEHOLD_ID}, ontvangen ${householdId}.`);
  }
  await verifyAuthorizationMembershipFixture(request, householdId);

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
  await page.getByLabel('E-mail').fill(OWNER_EMAIL);
  await page.getByLabel('Wachtwoord').fill(requireCredential(OWNER_PASSWORD, 'regressie-eigenaar wachtwoord'));
  await page.getByRole('button', { name: 'Inloggen' }).click();
  await page.waitForURL('**/home');
}

export {
  API_URL,
  DEMO_HOUSEHOLD_ID,
  PLATFORM_EMAIL,
  PLATFORM_PASSWORD,
  OWNER_EMAIL,
  OWNER_PASSWORD,
  AUTHORIZATION_FIXTURE_MEMBER_EMAIL,
  AUTHORIZATION_FIXTURE_MEMBER_ROLE,
};
