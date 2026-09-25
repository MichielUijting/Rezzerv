import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

test.describe('Mobiele Boodschappen', () => {
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
        quantity: 1,
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
        quantity: 1,
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
      { source_type: 'household_article', source_id: 'household-article-broccoli', label: 'Broccoli', article_name: 'Broccoli', article_group_name: 'Groente', product_type_name: 'Broccoli' },
      { source_type: 'household_article', source_id: 'household-article-broodjes', label: 'Broodjes', article_name: 'Broodjes', article_group_name: 'Brood', product_type_name: 'Broodjes' },
      { source_type: 'product_type', source_id: 'product-type-banaan', label: 'Banaan', article_name: 'Banaan', article_group_name: 'Fruit', product_type_name: 'Banaan' },
      { source_type: 'article_group', source_id: 'article-group-fruit', label: 'Fruit', article_name: 'Fruit', article_group_name: 'Fruit', product_type_name: '' },
      { source_type: 'product_type', source_id: 'product-type-groente', label: 'Groente', article_name: 'Groente', article_group_name: 'Groente', product_type_name: 'Groente' },
    ]

    await page.route('**/api/shopping-list/catalog-search?*', async (route) => {
      const url = new URL(route.request().url())
      expect(url.searchParams.get('limit')).toBe('5')
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
      const existing = items.find((item) =>
        item.source_type === payload.source_type && item.source_id === payload.source_id
      )
      if (existing) {
        existing.quantity = Number(existing.quantity ?? 1) + Number(payload.quantity ?? 1)
        existing.checked = false
        await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(existing) })
        return
      }
      const item = {
        id: 'mobile-bananen',
        shopping_list_id: activeListId,
        household_id: '0',
        article_name: payload.article_name,
        article_group_name: payload.article_group_name || '',
        product_type_name: payload.product_type_name || '',
        quantity: Number(payload.quantity ?? 1),
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
    await expect(page.getByText('Mijn boodschappen', { exact: true })).toBeVisible()
    await expect(page.getByText('2 artikelen • 2 nog te vinden', { exact: true })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Boodschappen', exact: true })).toBeVisible()
    await expect(page.getByLabel('Zoek in winkellijst')).toHaveCount(0)
    await expect(page.getByTestId('mobile-shopping-producttype')).toHaveCount(0)
    await expect(page.getByTestId('mobile-shopping-sort')).toHaveCount(0)
    await expect(page.getByText('Niet ingedeeld', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Suggesties', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Aanbiedingen', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Vaak gekocht', { exact: true })).toHaveCount(0)

    await expect(page.getByText('Zuivel', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Halfvolle melk', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Volkoren brood', { exact: true })).toHaveCount(0)

    const statusFilter = page.getByTestId('mobile-shopping-status-filter')
    await expect(statusFilter).not.toBeChecked()
    await page.getByLabel('Melk in kar leggen').check()
    await expect(page.getByText('2 artikelen • 1 nog te vinden', { exact: true })).toBeVisible()
    await expect(page.getByTestId('mobile-shopping-item-mobile-melk')).toHaveCount(0)

    await statusFilter.check()
    const melkCard = page.getByTestId('mobile-shopping-item-mobile-melk')
    await expect(melkCard).toBeVisible()
    await page.getByLabel('Melk uit kar halen').uncheck()
    await expect(melkCard).toHaveCount(0)
    await statusFilter.uncheck()
    const restoredMelkCard = page.getByTestId('mobile-shopping-item-mobile-melk')
    await expect(restoredMelkCard).toBeVisible()
    await expect(restoredMelkCard.getByRole('button', { name: 'Bewerken' })).toHaveCount(0)
    await restoredMelkCard.getByRole('button', { name: 'Verhoog aantal van Melk' }).click()
    await expect(restoredMelkCard).toContainText('2')


    await page.getByRole('searchbox', { name: 'Artikel toevoegen', exact: true }).fill('ban')
    const candidateList = page.getByTestId('mobile-shopping-candidate-list')
    await expect(candidateList).toBeVisible()
    await expect(candidateList.getByRole('option')).toHaveCount(5)
    await candidateList.getByRole('option', { name: 'Bananen — Huishoudartikel', exact: true }).click()
    await page.getByTestId('mobile-shopping-add').click()
    await expect(page.getByText('3 artikelen • 2 nog te vinden', { exact: true })).toBeVisible()
    await expect(page.getByText('Bananen', { exact: true })).toBeVisible()

    const addSearchbox = page.getByRole('searchbox', { name: 'Artikel toevoegen', exact: true })
    for (let repeat = 0; repeat < 2; repeat += 1) {
      await addSearchbox.fill('ban')
      await page.getByTestId('mobile-shopping-candidate-list').getByRole('option', { name: 'Bananen — Huishoudartikel', exact: true }).click()
      await page.getByTestId('mobile-shopping-add').click()
      await expect(addSearchbox).toHaveValue('')
    }
    await expect(page.getByText('3 artikelen • 2 nog te vinden', { exact: true })).toBeVisible()
    const bananaCard = page.getByTestId('mobile-shopping-item-mobile-bananen')
    await expect(bananaCard.getByText('3', { exact: true })).toBeVisible()
    await expect(page.getByTestId('mobile-shopping-item-mobile-bananen')).toHaveCount(1)

    await expect(page.getByLabel('Selecteer Brood')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Verwijderen' })).toHaveCount(0)


    await page.getByTestId('mobile-shopping-complete').click()
    await expect(page.getByTestId('shopping-complete-confirmation')).toBeVisible()
    await page.getByTestId('shopping-complete-confirmation-primary-button').click()
    await expect(page.getByText('Nog geen artikelen bij Boodschappen.', { exact: true })).toBeVisible()

    await expectNoConsoleErrors(consoleErrors)
  })
})
