import { expect } from '@playwright/test';

const EXPECTED_AUTHORIZATION_RESOURCE_ERROR = /^Failed to load resource: the server responded with a status of 403 \(Forbidden\)$/;

export function attachConsoleErrorCollector(page) {
  const consoleErrors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      const text = message.text();
      // Een 403 is binnen het autorisatiemodel een geldige, bewust afgedwongen
      // weigering. De functionele tests controleren afzonderlijk dat de pagina
      // en toegestane acties correct blijven werken. Andere consolefouten blijven rood.
      if (!EXPECTED_AUTHORIZATION_RESOURCE_ERROR.test(text)) {
        consoleErrors.push(text);
      }
    }
  });

  page.on('pageerror', (error) => {
    consoleErrors.push(error.message);
  });

  return consoleErrors;
}

export async function expectNoConsoleErrors(consoleErrors) {
  expect(consoleErrors).toEqual([]);
}

export async function expectAnyVisible(page, candidates, description = 'verwachte tekst') {
  for (const candidate of candidates) {
    const locator = typeof candidate === 'string'
      ? page.getByText(candidate, { exact: false })
      : page.getByText(candidate);

    const count = await locator.count().catch(() => 0);
    for (let index = 0; index < count; index++) {
      if (await locator.nth(index).isVisible().catch(() => false)) {
        return;
      }
    }
  }

  throw new Error(`Geen zichtbare match gevonden voor ${description}: ${candidates.map(String).join(' | ')}`);
}

export async function expectRouteLoads(page, path, expectedTexts) {
  await page.goto(path);
  await expect(page.locator('body')).toBeVisible();

  await expect.poll(
    async () => {
      for (const candidate of expectedTexts) {
        const locator = typeof candidate === 'string'
          ? page.getByText(candidate, { exact: false })
          : page.getByText(candidate);
        const count = await locator.count().catch(() => 0);
        for (let index = 0; index < count; index++) {
          if (await locator.nth(index).isVisible().catch(() => false)) {
            return true;
          }
        }
      }
      return false;
    },
    {
      message: `Geen zichtbare match gevonden voor route ${path}: ${expectedTexts.map(String).join(' | ')}`,
      timeout: 15000,
      intervals: [100, 250, 500, 1000],
    },
  ).toBe(true);

  await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
}
