import { test, expect } from '@playwright/test';
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js';

test.describe('Artikeldetail frontend-regressie', () => {
  test('Stabiele artikelroute gebruikt de universele naam, conditionele Locaties en standaard meldingoverlay', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page);
    const failedResponses = [];
    page.on('response', (response) => {
      if (response.status() >= 400) {
        failedResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
      }
    });
    const articleId = 'household-article-mosterd';
    const universalArticleName = 'Mosterd fijne Dijon extra lange universele artikelnaam';
    const receiptArticleText = 'MOSTERD DIJON 250G';
    let primaryUseCase = 'waar_inhuis';
    let historyShouldFail = false;

    await page.route('**/api/onboarding', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ primary_use_case: primaryUseCase }),
      });
    });

    await page.route('**/api/settings/article-field-visibility', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          overview: {},
          stock: {},
          locations: {},
          history: {},
          analytics: {},
        }),
      });
    });

    await page.route('**/api/dev/inventory-preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rows: [
            {
              id: articleId,
              artikel: universalArticleName,
              locatie: 'Voorraadkast',
              sublocatie: 'Plank 2',
              aantal: 3,
            },
          ],
        }),
      });
    });

    await page.route(`**/api/household-articles/${articleId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          article_id: articleId,
          article_name: universalArticleName,
          brand_or_maker: 'Rezzerv testmerk',
          article_type: 'Verbruiksartikel',
          notes: 'Universele naam is leidend.',
          total_quantity: 3,
          main_location: 'Voorraadkast',
          sub_location: 'Plank 2',
        }),
      });
    });

    await page.route(`**/api/household-articles/${articleId}/automation-override`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          article_id: articleId,
          household_article_id: articleId,
          requested_article_id: articleId,
          mode: 'follow_household',
          has_explicit_override: false,
          consumable: true,
          article_name: universalArticleName,
        }),
      });
    });

    await page.route(`**/api/household-articles/${articleId}/events`, async (route) => {
      if (historyShouldFail) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Historiebron tijdelijk niet beschikbaar' }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'event-mosterd-1',
              event_type: 'purchase',
              created_at: '2026-07-17T12:00:00Z',
              old_quantity: 1,
              new_quantity: 3,
              quantity: 2,
              location_label: 'Voorraadkast / Plank 2',
              source: 'regression',
              note: universalArticleName,
            },
          ],
        }),
      });
    });

    await page.goto(`/voorraad/${encodeURIComponent(articleId)}`);

    await expect(page).toHaveURL(new RegExp(`/voorraad/${articleId}$`));
    await expect(page.getByTestId('article-detail-page')).toBeVisible();
    await expect(page.getByTestId('article-detail-title')).toHaveText(
      `Artikel details: ${universalArticleName}`,
    );

    await expect(page.getByTestId('app-header').getByText(`Artikel details: ${universalArticleName}`, { exact: true })).toBeVisible();
    await expect(page.getByText(receiptArticleText, { exact: true })).toHaveCount(0);

    for (const tabName of ['Overzicht', 'Voorraad', 'Locaties', 'Historie', 'Analyse']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible();
    }

    primaryUseCase = 'wat_inhuis';
    const onboardingRequest = page.waitForRequest((request) => request.url().includes('/api/onboarding'));
    await page.reload();
    await onboardingRequest;
    await expect(page.getByTestId('article-detail-page')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Locaties', exact: true })).toHaveCount(0);
    for (const tabName of ['Overzicht', 'Voorraad', 'Historie', 'Analyse']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible();
    }

    failedResponses.length = 0;
    historyShouldFail = true;
    await page.reload();
    const feedback = page.getByTestId('app-feedback-error');
    await expect(feedback).toBeVisible();
    await expect(feedback.getByText('Melding', { exact: true })).toBeVisible();
    await expect(feedback.getByText(/Live artikelhistorie kon niet worden geladen/)).toBeVisible();
    await expect(
      page.locator('.rz-article-detail-alert').filter({ hasText: 'Live artikelhistorie kon niet worden geladen.' }),
    ).toHaveCount(0);

    const historyFailures = failedResponses.filter((entry) => entry.startsWith('503 GET '));
    expect(historyFailures.length).toBeGreaterThan(0);
    expect(historyFailures.every((entry) => entry.includes(`/api/household-articles/${articleId}/events`))).toBe(true);
    expect(failedResponses.filter((entry) => !entry.startsWith('503 GET '))).toEqual([]);
    await expectNoConsoleErrors(consoleErrors);
  });
});