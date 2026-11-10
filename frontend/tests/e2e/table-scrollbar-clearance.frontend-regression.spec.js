import { test, expect } from '@playwright/test'

// Shared Table is used by DataTable and the specialized stock/store wrappers.
test('horizontal scrollbar remains below the last row for all shared table wrappers', async ({ page }) => {
  await page.goto('/login')
  const layout = await page.evaluate(() => {
    const classes = ['rz-table-wrapper', 'rz-table-wrapper rz-stock-table-wrapper',
      'rz-table-wrapper rz-store-batch-table-wrapper']
    return classes.map((className) => {
      const wrapper = document.createElement('div')
      wrapper.className = className
      wrapper.style.cssText = [
        'position:fixed', 'left:12px', 'top:12px', 'width:300px',
        'max-height:210px', 'z-index:99999',
        '--rz-table-header-row-height:40px',
        '--rz-table-filter-row-height:38px',
        '--rz-table-body-row-height:48px',
        '--rz-table-visible-row-count:10',
      ].join(';')
      const table = document.createElement('table')
      table.className = 'rz-table'
      table.style.cssText = 'width:950px; min-width:950px; border-collapse:collapse'
      const body = document.createElement('tbody')
      for (let i = 0; i < 10; i += 1) {
        const row = document.createElement('tr')
        row.style.height = '48px'
        const cell = document.createElement('td')
        cell.textContent = 'Controle artikel ' + i
        row.appendChild(cell)
        body.appendChild(row)
      }
      table.appendChild(body)
      wrapper.appendChild(table)
      document.body.appendChild(wrapper)
      wrapper.scrollTop = wrapper.scrollHeight
      const computed = getComputedStyle(wrapper)
      const rect = wrapper.getBoundingClientRect()
      const last = body.lastElementChild.getBoundingClientRect()
      const result = {
        className, paddingBottom: Number.parseFloat(computed.paddingBottom),
        hasHorizontalOverflow: wrapper.scrollWidth > wrapper.clientWidth,
        hasVerticalOverflow: wrapper.scrollHeight > wrapper.clientHeight,
        clearSpace: rect.bottom - last.bottom,
      }
      wrapper.remove()
      return result
    })
  })
  for (const result of layout) {
    expect(result.hasHorizontalOverflow, result.className).toBe(true)
    expect(result.hasVerticalOverflow, result.className).toBe(true)
    expect(result.paddingBottom, result.className).toBeGreaterThanOrEqual(24)
    expect(result.clearSpace, result.className).toBeGreaterThanOrEqual(12)
  }
})
