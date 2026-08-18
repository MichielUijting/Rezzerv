import { test, expect } from '@playwright/test'
import {
  attachConsoleErrorCollector,
  expectNoConsoleErrors,
} from './helpers/rezzervAssertions.js'

test.describe('Winkelen kolomcontrols', () => {
  test('titelrij heeft bulkcheckbox en echte kolomgrens blijft visueel resizebaar', async ({ page }) => {
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
    await expect(table).toHaveClass(/rz-table--resizable-columns/)
    await expect(page.getByLabel('Selecteer Melk')).toBeVisible()
    await expect(page.getByLabel('Selecteer Pasta')).toBeVisible()

    const firstHeaderCell = table.locator('thead tr:first-child th').first()
    const selectAll = firstHeaderCell.getByRole('checkbox', { name: 'Selecteer alle zichtbare rijen' })
    await expect(selectAll).toBeVisible()
    await expect(table.locator('thead tr:nth-child(2) th').first().getByRole('checkbox')).toHaveCount(0)

    await selectAll.check()
    await expect(page.getByLabel('Selecteer Melk')).toBeChecked()
    await expect(page.getByLabel('Selecteer Pasta')).toBeChecked()
    await selectAll.uncheck()
    await expect(page.getByLabel('Selecteer Melk')).not.toBeChecked()
    await expect(page.getByLabel('Selecteer Pasta')).not.toBeChecked()

    const articleHeader = table.getByRole('columnheader', { name: 'Artikel sorteren', exact: true })
    const productTypeHeader = table.getByRole('columnheader', { name: 'Producttype sorteren', exact: true })

    const articleBefore = await articleHeader.boundingBox()
    const productTypeBefore = await productTypeHeader.boundingBox()
    if (!articleBefore || !productTypeBefore) throw new Error('Kolomkoppen hebben geen meetbare browserpositie.')

    const boundaryPoint = {
      x: productTypeBefore.x + 2,
      y: productTypeBefore.y + productTypeBefore.height / 2,
    }

    await page.mouse.move(boundaryPoint.x, boundaryPoint.y)
    await page.mouse.down()
    await expect.poll(() => page.evaluate(() => document.body.classList.contains('rz-table-column-resizing'))).toBe(true)
    await page.mouse.move(boundaryPoint.x + 90, boundaryPoint.y, { steps: 6 })

    const duringResize = await page.evaluate(() => {
      const tableElement = document.querySelector('[data-testid="shopping-list-table"]')
      const article = tableElement?.querySelector('thead tr:first-child th:nth-child(2)')
      const productType = tableElement?.querySelector('thead tr:first-child th:nth-child(3)')
      const articleCol = tableElement?.querySelector('colgroup col:nth-child(2)')
      return {
        bodyResizing: document.body.classList.contains('rz-table-column-resizing'),
        articleColStyleWidth: articleCol?.style.width || '',
        tableStyleWidth: tableElement?.style.width || '',
        articleRenderedWidth: article?.getBoundingClientRect().width || 0,
        productTypeRenderedX: productType?.getBoundingClientRect().x || 0,
      }
    })
    console.log(`WINKELEN_RESIZE_DIAGNOSTIC ${JSON.stringify(duringResize)}`)
    expect(duringResize.bodyResizing).toBe(true)
    expect(Number.parseFloat(duringResize.articleColStyleWidth)).toBeGreaterThan(articleBefore.width + 70)

    await page.mouse.up()

    await expect.poll(async () => (await articleHeader.boundingBox())?.width || 0).toBeGreaterThan(articleBefore.width + 70)
    const articleAfterGrow = await articleHeader.boundingBox()
    const productTypeAfterGrow = await productTypeHeader.boundingBox()
    if (!articleAfterGrow || !productTypeAfterGrow) throw new Error('Gerenderde breedte ontbreekt na vergroten.')
    expect(productTypeAfterGrow.x).toBeGreaterThan(productTypeBefore.x + 70)

    await table.getByRole('button', { name: 'Gekocht sorteren', exact: true }).click()
    const articleAfterRerender = await articleHeader.boundingBox()
    if (!articleAfterRerender) throw new Error('Artikelbreedte ontbreekt na rerender.')
    expect(articleAfterRerender.width).toBeGreaterThan(articleBefore.width + 70)

    const productTypeBeforeShrink = await productTypeHeader.boundingBox()
    if (!productTypeBeforeShrink) throw new Error('Producttype-kolomkop ontbreekt voor verkleinen.')
    const shrinkBoundaryPoint = {
      x: productTypeBeforeShrink.x + 2,
      y: productTypeBeforeShrink.y + productTypeBeforeShrink.height / 2,
    }

    await page.mouse.move(shrinkBoundaryPoint.x, shrinkBoundaryPoint.y)
    await page.mouse.down()
    await page.mouse.move(shrinkBoundaryPoint.x - 55, shrinkBoundaryPoint.y, { steps: 5 })
    await page.mouse.up()

    await expect.poll(async () => (await articleHeader.boundingBox())?.width || 0).toBeLessThan(articleAfterGrow.width - 35)

    await expectNoConsoleErrors(consoleErrors)
  })
})
