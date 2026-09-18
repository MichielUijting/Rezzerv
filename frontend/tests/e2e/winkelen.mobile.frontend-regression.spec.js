import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

test.describe('Mobiel Winkelen', () => {
  test('gebruikt bestaande winkellijstfuncties in de mobiele kernflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const consoleErrors = attachConsoleErrorCollector(page)

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
          permissions: {
            'shopping_list.view': true,
            'shopping_list.update': true,
            'shopping_list.manage': true,
          },
          supported_permissions: [
            'shopping_list.view',
            'shopping_list.update',
            'shopping_list.manage',
          ],
          is_frontteam: false,
          is_platform_superuser: false,
        }),
      })
    })

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
          product_configuration: {
            location_tracking_level: 'global',
          },
        }),
      })
    })

    let activeListId = 'shopping-mobile-active-1'
    let items = [
      {
        id: 'mobile-melk',
        shopping_list_id: activeListId,
        household_id: '0',
        article_name: 'Melk',
        article_group_name: 'Zuivel',
        product_type_name: 'Halfvolle melk',
        size: '1 liter',
        note: '',
        checked: false,
        source_type: 'household_article',
        source_id: 'household-article-melk',
      },
      {
        id: 'mobile-brood',
        shopping_list_id: activeListId,
        household_id: '0',
        article_name: 'Brood',
        article_group_name: 'Brood',
        product_type_name: 'Volkoren brood',
        size: '',
        note: 'Gesneden',
        checked: false,
        source_type: 'product_type',
        source_id: 'product-type-brood',
      },
    ]

    const candidates = [
      {
        source_type: 'household_article',
        source_id: 'household-article-bananen',
        label: 'Bananen',
        article_name: 'Bananen',
        article_group_name: 'Fruit',
        product_type_name: 'Banaan',
      },
    ]

    await page.route('**/api/shopping-list/catalog-search?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          scope: 'all',
          query: 'ban',
          items: candidates,
          total: candidates.length,
          counts: { household_article: 1, product_type: 0, article_group: 0 },
        }),
      })
    })

    await page.route('**/api/shopping-list', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: activeListId,
          household_id: '0',
          status: 'active',
          items,
          item_count: items.length,
        }),
      })
    })

    await page.route('**/api/shopping-list/items', async (route) => {
      if (route.request().method() !== 'POST') return route.fallback()
      const payload = JSON.parse(route.request().postData() || '{}')
      const item = {
        id: 'mobile-bananen',
        shopping_list_id: activeListId,
        household_id: '0',
        article_name: payload.article_name,
        article_group_name: payload.article_group_name || '',
        product_type_name: payload.product_type_name || '',
        size: '',
        note: '',
        checked: false,
        source_type: payload.source_type,
        source_id: payload.source_id,
      }
      items = [...items, item]
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(item) })
    })

    await page.route('**/api/shopping-list/items/*', async (route) => {
      const itemId = decodeURIComponent(route.request().url().split('/').pop())
      if (route.request().method() === 'PUT') {
        const patch = JSON.parse(route.request().postData() || '{}')
        items = items.map((item) => item.id === itemId ? { ...item, ...patch } : item)
        const updated = items.find((item) => item.id === itemId)
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(updated) })
        return
      }
      if (route.request().method() === 'DELETE') {
        items = items.filter((item) => item.id !== itemId)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      return route.fallback()
    })

    await page.route('**/api/shopping-list/complete', async (route) => {
      const completedListId = activeListId
      activeListId = 'shopping-mobile-active-2'
      const completedItemCount = items.length
      items = []
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'completed',
          completed_list_id: completedListId,
          completed_item_count: completedItemCount,
          active_list_id: activeListId,
          items: [],
        }),
      })
    })

    await page.goto('/winkelen')
    await expect(page.getByTestId('mobile-shopping-page')).toBeVisible()
    await expect(page.getByTestId('shopping-page')).toHaveCount(0)
    await expect(page.getByText('Mijn lijst', { exact: true })).toBeVisible()
    await expect(page.getByText('2 artikelen • 2 nog te kopen', { exact: true })).toBeVisible()
    await expect(page.getByText('Suggesties', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Aanbiedingen', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Vaak gekocht', { exact: true })).toHaveCount(0)

    await expect(page.getByText('Zuivel', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Brood', { exact: true }).first()).toBeVisible()

    await page.getByLabel('Gekocht Melk').check()
    await expect(page.getByText('2 artikelen • 1 nog te kopen', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: 'Bewerken' }).first().click()
    await page.getByLabel('Opmerking Melk').fill('Halfvol')
    await page.getByLabel('Opmerking Melk').blur()
    await expect(page.getByText('Halfvol', { exact: true })).toBeVisible()

    await page.getByLabel('Artikel toevoegen').fill('ban')
    await expect(page.getByTestId('mobile-shopping-result')).toBeEnabled()
    await page.getByTestId('mobile-shopping-result').click()
    await page.getByRole('option', { name: 'Bananen — Huishoudartikel' }).click()
    await page.getByTestId('mobile-shopping-add').click()
    await expect(page.getByText('3 artikelen • 2 nog te kopen', { exact: true })).toBeVisible()
    await expect(page.getByText('Bananen', { exact: true })).toBeVisible()

    await page.getByLabel('Zoek in winkellijst').fill('brood')
    await expect(page.getByText('Brood', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('Melk', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Filters wissen' }).click()

    await page.getByLabel('Selecteer Brood').check()
    await expect(page.getByText('1 geselecteerd', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Verwijderen' }).click()
    await expect(page.getByTestId('shopping-delete-confirmation')).toBeVisible()
    await page.getByTestId('shopping-delete-confirmation-primary-button').click()
    await expect(page.getByText('Brood', { exact: true })).toHaveCount(0)

    await page.getByTestId('mobile-shopping-complete').click()
    await expect(page.getByTestId('shopping-complete-confirmation')).toBeVisible()
    await page.getByTestId('shopping-complete-confirmation-primary-button').click()
    await expect(page.getByText('Nog geen artikelen op de winkellijst.', { exact: true })).toBeVisible()

    await expectNoConsoleErrors(consoleErrors)
  })
})
