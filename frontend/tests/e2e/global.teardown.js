const API_URL = process.env.PLAYWRIGHT_API_URL || 'http://127.0.0.1:8001';
const DEV_ADMIN_TOKEN = process.env.PLAYWRIGHT_ADMIN_TOKEN || 'rezzerv-dev-token::admin@rezzerv.local';

async function globalTeardown() {
  const response = await fetch(`${API_URL}/api/testing/fixtures/cleanup`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${DEV_ADMIN_TOKEN}`,
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Regression fixture cleanup failed with ${response.status}: ${body}`);
  }
}

export default globalTeardown;
