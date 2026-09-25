import { test, expect } from '@playwright/test';
import { mergeIncomingFormStatePreservingDirtyFields } from '../../src/features/articles/lib/householdSettingsFormState.js';
import { attachConsoleErrorCollector } from './helpers/rezzervAssertions.js';

test.describe('Artikeldetail frontend-regressie', () => {
  test('Late huishoudinstellingen overschrijven geen velden die de gebruiker al heeft gewijzigd', () => {
    const dirtyFields = new Set();
    let formState = {
      min_stock: '',
      ideal_stock: '',
      notes: '',
    };

    dirtyFields.add('min_stock');
    formState = { ...formState, min_stock: '0' };
    formState = mergeIncomingFormStatePreservingDirtyFields(
      formState,
      { min_stock: '', ideal_stock: '', notes: 'serverwaarde' },
      dirtyFields,
    );

    expect(formState).toEqual({
      min_stock: '0',
      ideal_stock: '',
      notes: 'serverwaarde',
    });

    dirtyFields.add('ideal_stock');
    formState = { ...formState, ideal_stock: '1' };
    formState = mergeIncomingFormStatePreservingDirtyFields(
      formState,
      { min_stock: '', ideal_stock: '9', notes: 'nieuwere serverwaarde' },
      dirtyFields,
    );

    expect(formState).toEqual({
      min_stock: '0',
      ideal_stock: '1',
      notes: 'nieuwere serverwaarde',
    });

    dirtyFields.clear();
    formState = mergeIncomingFormStatePreservingDirtyFields(
      formState,
      { min_stock: '2', ideal_stock: '3', notes: 'opgeslagen serverwaarde' },
      dirtyFields,
    );

    expect(formState).toEqual({
      min_stock: '2',
      ideal_stock: '3',
      notes: 'opgeslagen serverwaarde',
    });
  });

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
    let locationTrackingLevel = 'global';
    let historyShouldFail = false;
    let inventoryShouldFail = false;

    await page.route('**/api/onboarding', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          primary_use_case: primaryUseCase,
          product_configuration: {
            location_tracking_level: locationTrackingLevel,
          },
        }),
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
      if (inventoryShouldFail) {
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Voorraadbron tijdelijk niet beschikbaar' }),
        });
        return;
      }
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
    const onboardingUseCaseRequest = page.waitForRequest((request) => request.url().includes('/api/onboarding'));
    await page.reload();
    await onboardingUseCaseRequest;
    await expect(page.getByTestId('article-detail-page')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Locaties', exact: true })).toBeVisible();

    locationTrackingLevel = 'none';
    const onboardingLocationPolicyRequest = page.waitForRequest((request) => request.url().includes('/api/onboarding'));
    await page.reload();
    await onboardingLocationPolicyRequest;
    await expect(page.getByTestId('article-detail-page')).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Locaties', exact: true })).toHaveCount(0);
    for (const tabName of ['Overzicht', 'Voorraad', 'Historie', 'Analyse']) {
      await expect(page.getByRole('tab', { name: tabName, exact: true })).toBeVisible();
    }

    failedResponses.length = 0;
    historyShouldFail = true;
    await page.reload();
    let feedback = page.getByTestId('app-feedback-error');
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

    await feedback.getByTestId('app-feedback-error-ok-button').click();
    await expect(feedback).toHaveCount(0);

    failedResponses.length = 0;
    historyShouldFail = false;
    inventoryShouldFail = true;
    await page.reload();
    feedback = page.getByTestId('app-feedback-error');
    await expect(feedback).toBeVisible();
    await expect(feedback.getByText('Melding', { exact: true })).toBeVisible();
    await expect(feedback.getByText(/Live artikelvoorraad kon niet worden geladen/)).toBeVisible();
    await expect(page.locator('.rz-article-detail-alert')).toHaveCount(0);
    await expect(feedback.getByTestId('app-feedback-technical-toggle')).toBeVisible();
    await feedback.getByTestId('app-feedback-technical-toggle').click();
    await expect(feedback.getByTestId('app-feedback-technical-details')).toContainText('Voorraadbron tijdelijk niet beschikbaar');

    const inventoryFailures = failedResponses.filter((entry) => entry.startsWith('503 GET '));
    expect(inventoryFailures.length).toBeGreaterThan(0);
    expect(inventoryFailures.every((entry) => entry.includes('/api/dev/inventory-preview'))).toBe(true);
    expect(failedResponses.filter((entry) => !entry.startsWith('503 GET '))).toEqual([]);

    // Chromium reports the intentionally simulated 503s as console network errors.
    // Those are part of these failure-path tests, not application console failures.
    const unexpectedConsoleErrors = consoleErrors.filter(
      (entry) => !(
        entry.includes('Failed to load resource')
        && (
          entry.includes(`/api/household-articles/${articleId}/events`)
          || entry.includes('/api/dev/inventory-preview')
        )
      ),
    );
    expect(unexpectedConsoleErrors).toEqual([]);
  });

  test('mobiele voorkeurswinkel gebruikt de standaard zoekbare scroll-dropdown zonder layoutverschuiving', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const consoleErrors = attachConsoleErrorCollector(page);
    const articleId = 'household-article-dropdown-test';
    const articleName = 'Dropdown testartikel';
    let savedFavoriteStore = '';

    await page.route('**/api/session', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: { id: 'test-admin@rezzerv.local', email: 'test-admin@rezzerv.local' },
          user_id: 'test-admin@rezzerv.local',
          email: 'test-admin@rezzerv.local',
          active_household_id: '0',
          active_household_name: 'Systeemhuishouden',
          context_type: 'regular',
          role: 'owner',
          display_role: 'owner',
          permissions: {},
          supported_permissions: [],
          is_frontteam: false,
          is_platform_superuser: false,
        }),
      });
    });

    await page.route('**/api/onboarding', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          onboarding_status: 'completed',
          onboarding_step: 'done',
          primary_use_case: 'wat_inhuis',
          initial_choice_required: false,
          shared_household_minimum_required: false,
          can_manage: true,
          product_configuration: { location_tracking_level: 'none' },
        }),
      });
    });

    await page.route('**/api/dev/inventory-preview?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          rows: [{
            id: 'inventory-dropdown-test',
            household_article_id: articleId,
            artikel: articleName,
            aantal: 2,
          }],
        }),
      });
    });

    await page.route('**/api/store-providers', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { name: 'Albert Heijn' },
            { name: 'Aldi' },
            { name: 'Coop' },
            { name: 'Dirk' },
            { name: 'Jumbo' },
            { name: 'Kassabon' },
            { name: 'Lidl' },
            { name: 'Plus' },
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
          household_article_id: articleId,
          article_name: articleName,
          article_group_name: 'Testgroep',
          settings: {
            favorite_store: '',
            min_stock: null,
            notes: '',
          },
        }),
      });
    });

    await page.route(`**/api/household-articles/${articleId}/events`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      });
    });

    await page.route(`**/api/household-articles/${articleId}/settings`, async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}');
      savedFavoriteStore = String(payload.favorite_store || '');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ settings: payload }),
      });
    });

    await page.goto(`/voorraad/${articleId}`);
    await expect(page.getByTestId('mobile-article-detail-page')).toBeVisible();

    await page.getByTestId('mobile-article-tab-household').click();
    const trigger = page.getByTestId('mobile-article-favorite-store-select');
    const averagePrice = page.getByTestId('article-details-input-average_price');
    await expect(trigger).toBeVisible();
    await expect(averagePrice).toBeVisible();
    const before = await averagePrice.boundingBox();
    expect(before).not.toBeNull();

    await trigger.click();

    const popover = page.getByTestId('mobile-article-favorite-store-select-popover');
    const search = page.getByTestId('mobile-article-favorite-store-select-search');
    const listbox = page.getByTestId('mobile-article-favorite-store-select-listbox');

    await expect(popover).toBeVisible();
    await expect(search).toBeVisible();
    await expect(search).toHaveAttribute('placeholder', 'Zoeken…');
    await expect(listbox.getByRole('option')).toHaveCount(9);

    const popoverMetrics = await popover.evaluate((element) => ({
      position: getComputedStyle(element).position,
    }));
    expect(popoverMetrics.position).toBe('fixed');

    const listMetrics = await listbox.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      overflowY: getComputedStyle(element).overflowY,
    }));
    expect(listMetrics.clientHeight).toBeLessThanOrEqual(220);
    expect(listMetrics.scrollHeight).toBeGreaterThan(listMetrics.clientHeight);
    expect(listMetrics.overflowY).toBe('auto');

    const after = await averagePrice.boundingBox();
    expect(after).not.toBeNull();
    expect(Math.abs(after.y - before.y)).toBeLessThan(1);

    await listbox.hover();
    await page.mouse.wheel(0, 500);
    await expect.poll(async () => listbox.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);

    await search.fill('Plus');
    await expect(listbox.getByRole('option')).toHaveCount(1);
    await expect(listbox.getByRole('option', { name: 'Plus', exact: true })).toBeVisible();
    await listbox.getByRole('option', { name: 'Plus', exact: true }).click();

    await expect(trigger).toContainText('Plus');
    await page.getByTestId('article-household-settings-save').click();
    await expect.poll(() => savedFavoriteStore).toBe('Plus');
    expect(consoleErrors).toEqual([]);
  });
});