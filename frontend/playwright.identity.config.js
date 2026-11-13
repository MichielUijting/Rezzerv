import { defineConfig, devices } from '@playwright/test'

// Self-contained browser regression for Artikelbeheer identity confirmation.
// All backend routes are mocked; real authorization is covered separately by
// backend HTTP tests and the isolated PostgreSQL chain suite.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: [
    '**/article-identity-confirmation.frontend-regression.spec.js',
    '**/ed2-catalog-return-manual-barcode.frontend-regression.spec.js',
  ],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['line'], ['html', { outputFolder: 'playwright-report-identity', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium-identity', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
