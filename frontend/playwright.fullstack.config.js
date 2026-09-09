import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5174'
const f509AuthorityEnabled = Boolean(String(process.env.PLAYWRIGHT_F5_09_EMAIL || '').trim())
const fullstackTestMatch = f509AuthorityEnabled
  ? /(?:p0-(?:onboarding|account-session|authorization-isolation|receipt-inventory(?:-(?:locations-off|idempotency))?|receipt-nonphysical|kassa-review|article-identity-history|platform-authority|unpacking|inventory-correction|almost-out-recalculation)|f5-unclassified-unpacking-choice)\.fullstack\.spec\.js/
  : /p0-(onboarding|account-session|authorization-isolation|receipt-inventory(?:-(?:locations-off|idempotency))?|receipt-nonphysical|kassa-review|article-identity-history|platform-authority|unpacking|inventory-correction|almost-out-recalculation)\.fullstack\.spec\.js/

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: {
    timeout: 12_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['line'], ['html', { outputFolder: 'playwright-report-fullstack', open: 'never' }]],
  use: {
    baseURL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'chromium-fullstack',
      testMatch: fullstackTestMatch,
      use: {
        ...devices['Desktop Chrome'],
      },
    },
  ],
})
