import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

test.describe('Winkelen kolomcontrols', () => {
  test('titelrij heeft bulkcheckbox en kolomrand is echt sleepbaar', async ({ page }) => {
    const consoleErrors = attachConsoleErrorCollector(page)
    const items = [
      {
        id: 'shopping-item-melk',
        shopping_list_id: 'shopping-list-active-controls',
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
        id: 'shopping-item-pasta',
        shopping_list_id: 'shopping-list-active-controls',
        household_id: '0',
        article_name: 'Pasta',
        article_group_name: 'Houdbaar',
        product_type_name: 'Pasta',
        size: '500 g',
        note: '',
        checked: false,
        source_type: 'product_type',
        source_id: 'product-type-pasta',
      },
    ]

    await page.route('**/api/shopping-list', async (route) => {
      if (route.request().method() !== 'GET') return route.fallback()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'shopping-list-active-controls',
          household_id: '0',
          status: 'active',
          items,
          item_count: items.length,
        }),
      })
    })

    await page.goto('/winkelen')

    const table = page.getByTestId('shopping-list-table')
    await expect(table).toBeVisible()
    await expect(page.getByLabel('Selecteer Melk')).toBeVisible()
    await expect(page.getByLabel('Selecteer Pasta')).toBeVisible()

    const firstHeaderCell = table.locator('thead tr:first-child th').first()
    const selectAll = firstHeaderCell.getByRole('checkbox', { name: 'Selecteer alle zichtbare rijen' })
    await expect(selectAll).toBeVisible()
    await expect(table.locator('thead tr:nth-child(2) th').first().getByRole('checkbox')).toHaveCount(0)

    await expect(page.getByLabel('Selecteer Melk')).not.toBeChecked()
    await expect(page.getByLabel('Selecteer Pasta')).not.toBeChecked()

    await selectAll.check()
    await expect(page.getByLabel('Selecteer Melk')).toBeChecked()
    await expect(page.getByLabel('Selecteer Pasta')).toBeChecked()
    await expect(selectAll).toBeChecked()

    await selectAll.uncheck()
    await expect(page.getByLabel('Selecteer Melk')).not.toBeChecked()
    await expect(page.getByLabel('Selecteer Pasta')).not.toBeChecked()
    await expect(selectAll).not.toBeChecked()

    const articleHeader = table.getByRole('columnheader', { name: 'Artikel sorteren', exact: true })
    const articleHeaderBox = await articleHeader.boundingBox()
    if (!articleHeaderBox) throw new Error('Artikel-kolomkop heeft geen meetbare browserpositie.')

    const edgePoint = {
      x: articleHeaderBox.x + articleHeaderBox.width - 8,
      y: articleHeaderBox.y + articleHeaderBox.height / 2,
    }
    const edgeTarget = await page.evaluate(({ x, y }) => {
      const element = document.elementFromPoint(x, y)
      if (!element) return null
      return {
        role: element.getAttribute('role'),
        label: element.getAttribute('aria-label'),
        cursor: window.getComputedStyle(element).cursor,
      }
    }, edgePoint)

    expect(edgeTarget).toEqual({
      role: 'separator',
      label: 'Kolom breedte aanpassen',
      cursor: 'col-resize',
    })

    const articleColumn = table.locator('colgroup col').nth(1)
    const articleWidthBefore = Number.parseFloat(await articleColumn.evaluate((column) => column.style.width))

    await page.mouse.move(edgePoint.x, edgePoint.y)
    await page.mouse.down()
    await page.mouse.move(edgePoint.x + 80, edgePoint.y, { steps: 4 })
    await page.mouse.up()

    const articleWidthAfter = Number.parseFloat(await articleColumn.evaluate((column) => column.style.width))
    expect(articleWidthAfter).toBeGreaterThan(articleWidthBefore + 60)

    await expectNoConsoleErrors(consoleErrors)
  })
})
