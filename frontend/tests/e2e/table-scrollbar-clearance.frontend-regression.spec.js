import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'

// CSS layout tests do not depend on an authenticated session.
test.use({ storageState: { cookies: [], origins: [] } })

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


test('shared table pagination clears bottom scrollbar on stock, low-stock and catalog layouts', async ({ page }) => {
  await page.goto('/login')
  const measurements = await page.evaluate(() => {
    const types = ['rz-pagination', 'rz-external-databases-pagination', 'rz-data-table-controls']
    return types.map((type) => {
      const shell = document.createElement('section')
      shell.className = 'rz-data-table-shell'
      shell.style.cssText = 'position:fixed; left:10px; top:10px; width:320px; z-index:99999'
      const wrapper = document.createElement('div')
      wrapper.className = 'rz-table-wrapper'
      wrapper.style.cssText = 'max-height:110px; width:300px'
      const table = document.createElement('table')
      table.className = 'rz-table'
      table.style.cssText = 'width:900px; min-width:900px'
      const body = document.createElement('tbody')
      for (let i = 0; i < 8; i += 1) {
        const tr = document.createElement('tr')
        const td = document.createElement('td')
        td.style.height = '38px'
        td.textContent = 'Voorraadartikel ' + i
        tr.appendChild(td)
        body.appendChild(tr)
      }
      table.appendChild(body)
      wrapper.appendChild(table)
      const pager = document.createElement('nav')
      pager.className = type
      pager.textContent = '1 - 2 + 15'
      shell.append(wrapper, pager)
      document.body.appendChild(shell)
      const scrollBottom = wrapper.getBoundingClientRect().bottom
      const paginationTop = pager.getBoundingClientRect().top
      const horizontalOverflow = wrapper.scrollWidth > wrapper.clientWidth
      shell.remove()
      return { type, distance: paginationTop - scrollBottom, horizontalOverflow }
    })
  })
  for (const item of measurements) {
    expect(item.horizontalOverflow, item.type).toBe(true)
    expect(item.distance, item.type).toBeGreaterThanOrEqual(18)
  }
})


test('Bijna op retains column headings and filter fields during vertical table scroll', async ({ page }) => {
  const source = readFileSync(new URL('../../src/features/almostOut/AlmostOutPage.jsx', import.meta.url), 'utf8')
  expect(source).toContain('tableClassName="rz-stock-table rz-data-table--sticky-header rz-data-table--sticky-filters"')
  await page.goto('/login')
  const geometry = await page.evaluate(() => {
    const wrapper = document.createElement('div')
    wrapper.className = 'rz-table-wrapper'
    wrapper.style.cssText = 'position:fixed;top:20px;left:20px;width:430px;max-height:180px;z-index:9999'
    const table = document.createElement('table')
    table.className = 'rz-table rz-stock-table rz-data-table--sticky-header rz-data-table--sticky-filters'
    table.style.cssText = 'min-width:650px;width:650px;--rz-sticky-header-offset:42px'
    const header = document.createElement('thead')
    const title = document.createElement('tr')
    title.className = 'rz-table-header'
    const thTitle = document.createElement('th')
    thTitle.textContent = 'Huishoudnaam'
    title.appendChild(thTitle)
    const filters = document.createElement('tr')
    filters.className = 'rz-table-filters'
    const thFilter = document.createElement('th')
    thFilter.innerHTML = '<input placeholder="Filter">'
    filters.appendChild(thFilter)
    header.append(title, filters)
    const body = document.createElement('tbody')
    for (let i = 0; i < 16; i += 1) {
      const row = document.createElement('tr')
      const cell = document.createElement('td')
      cell.textContent = 'Artikel ' + i
      cell.style.height = '42px'
      row.appendChild(cell)
      body.appendChild(row)
    }
    table.append(header, body)
    wrapper.appendChild(table)
    document.body.appendChild(wrapper)
    wrapper.scrollTop = wrapper.scrollHeight
    const frame = wrapper.getBoundingClientRect()
    const titleRect = thTitle.getBoundingClientRect()
    const filterRect = thFilter.getBoundingClientRect()
    const computed = getComputedStyle(thFilter)
    const result = {
      hasScroll: wrapper.scrollHeight > wrapper.clientHeight,
      titleDistance: Math.abs(titleRect.top - frame.top),
      filterDistance: Math.abs(filterRect.top - (frame.top + titleRect.height)),
      titleSticky: getComputedStyle(thTitle).position,
      filterSticky: computed.position,
    }
    wrapper.remove()
    return result
  })
  expect(geometry.hasScroll).toBe(true)
  expect(geometry.titleSticky).toBe('sticky')
  expect(geometry.filterSticky).toBe('sticky')
  expect(geometry.titleDistance).toBeLessThanOrEqual(5)
  expect(geometry.filterDistance).toBeLessThanOrEqual(10)
})
