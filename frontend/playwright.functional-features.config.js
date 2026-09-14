import { defineConfig, devices } from '@playwright/test'

// Isolated frontend-only suite: all API traffic is mocked by the tests.
// No auth setup, provisioning, database, or global regression runner.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /(?:functional-feature-availability|platform-feature-flags)\.frontend-regression\.spec\.js/,
  workers: 1,
  reporter: 'line',
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || 'test-results-functional-features',
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:5187', screenshot: 'off', trace: 'off' },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5187 --strictPort',
    url: 'http://127.0.0.1:5187',
    reuseExistingServer: false,
  },
})
