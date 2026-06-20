import { expect } from '@playwright/test';

export function attachConsoleErrorCollector(page) {
  const consoleErrors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
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

    if (await locator.first().isVisible().catch(() => false)) {
      return;
    }
  }

  throw new Error(`Geen zichtbare match gevonden voor ${description}: ${candidates.map(String).join(' | ')}`);
}

export async function expectRouteLoads(page, path, expectedTexts) {
  await page.goto(path);
  await expect(page.locator('body')).toBeVisible();
  await expectAnyVisible(page, expectedTexts, `route ${path}`);
  await expect(page.getByText(/Application error|Uncaught|TypeError|ReferenceError/i)).toHaveCount(0);
}
