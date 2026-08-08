import { expect } from '@playwright/test';

export function attachConsoleErrorCollector(page) {
  const consoleErrors = [];
  const recordedResponses = new Set();

  page.on('console', (message) => {
    if (message.type() === 'error') {
      const location = message.location();
      const sourceUrl = String(location?.url || '').trim();
      const line = Number(location?.lineNumber || 0);
      const column = Number(location?.columnNumber || 0);
      const source = sourceUrl
        ? ` [bron: ${sourceUrl}${line ? `:${line}` : ''}${column ? `:${column}` : ''}]`
        : '';
      consoleErrors.push(`${message.text()}${source}`);
    }
  });

  page.on('response', (response) => {
    if (response.status() !== 403) return;

    const request = response.request();
    const detail = `HTTP 403 ${request.method()} ${response.url()}`;
    if (!recordedResponses.has(detail)) {
      recordedResponses.add(detail);
      consoleErrors.push(detail);
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
