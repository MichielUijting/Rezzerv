import { getLayer1Fixture } from './layer1RegressionFixture'
import { getRezzervVersionTag } from '../../../ui/version'

const FRAME_ID = 'rezzerv-layer3-runner-frame'
const WAIT_TIMEOUT = 9000
const POLL_INTERVAL = 100
const READY_ROW_COLOR = 'rgb(238, 246, 240)'
const INCOMPLETE_ROW_COLOR = 'rgb(255, 226, 184)'

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function waitForCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    function tick() {
      try {
        const result = check()
        if (result) return resolve(result)
      } catch {
        // blijf pollen
      }
      if (Date.now() - start >= timeout) return reject(new Error(errorMessage))
      window.setTimeout(tick, POLL_INTERVAL)
    }
    tick()
  })
}

function removeExistingFrame() {
  const existing = document.getElementById(FRAME_ID)
  if (existing) existing.remove()
}

function createHiddenFrame() {
  removeExistingFrame()
  const frame = document.createElement('iframe')
  frame.id = FRAME_ID
  frame.title = 'Layer 3 styleguide runner'
  frame.setAttribute('aria-hidden', 'true')
  Object.assign(frame.style, {
    position: 'fixed',
    left: '-10000px',
    top: '0',
    width: '1440px',
    height: '900px',
    opacity: '0',
    pointerEvents: 'none',
    border: '0',
    background: '#fff',
  })
  document.body.appendChild(frame)
  return frame
}

function getFrameDocument(frame) {
  return frame.contentDocument || frame.contentWindow?.document || null
}

async function navigateFrame(frame, path) {
  await new Promise((resolve, reject) => {
    let settled = false
    const timer = window.setTimeout(() => {
      if (settled) return
      settled = true
      reject(new Error(`Navigatie naar ${path} duurde te lang`))
    }, WAIT_TIMEOUT)

    function handleLoad() {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      resolve()
    }

    frame.addEventListener('load', handleLoad, { once: true })
    frame.src = path
  })

  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return doc && doc.readyState === 'complete'
  }, WAIT_TIMEOUT, `Pagina ${path} werd niet volledig geladen`)

  await delay(150)
}

function setInputValue(input, value) {
  const view = input?.ownerDocument?.defaultView || window
  const setter = Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new view.Event('input', { bubbles: true }))
  input.dispatchEvent(new view.Event('change', { bubbles: true }))
}

function setSelectValue(select, value) {
  const view = select?.ownerDocument?.defaultView || window
  const setter = Object.getOwnPropertyDescriptor(view.HTMLSelectElement.prototype, 'value')?.set
  setter?.call(select, value)
  select.dispatchEvent(new view.Event('input', { bubbles: true }))
  select.dispatchEvent(new view.Event('change', { bubbles: true }))
}

function clickElement(element) {
  const view = element?.ownerDocument?.defaultView || window
  element.dispatchEvent(new view.MouseEvent('click', { bubbles: true, cancelable: true, view }))
}

function getRegressionAuthHeaders() {
  try {
    const token = window.localStorage.getItem('rezzerv_token') || ''
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

async function requestJson(url, init = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...getRegressionAuthHeaders(),
      ...(init.headers || {}),
    },
    ...init,
  })
  if (!response.ok) {
    const message = await response.text().catch(() => '')
    throw new Error(message || `Request mislukt (${response.status})`)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return null
}


function persistLayer3ReceiptFixture(resolved, fixture = {}) {
  const nextFixture = {
    articleId: fixture.articleId || null,
    articleName: fixture.articleName || null,
    inventoryId: fixture.inventoryId || null,
    batchMatchText: fixture.batchMatchText || 'Jumbo',
    completeLineLabel: fixture.completeLineLabel || 'Magere yoghurt',
    incompleteLineLabel: fixture.incompleteLineLabel || 'Appelsap',
    batchId: resolved?.batchId || '',
    latestBatchId: resolved?.latestBatchId || resolved?.batchId || '',
    completeLineId: resolved?.completeLineId || '',
    incompleteLineId: resolved?.incompleteLineId || '',
  }
  try {
    window.localStorage.setItem('rezzerv_layer3_fixture', JSON.stringify(nextFixture))
  } catch {
    // negeer opslagfouten
  }
  return nextFixture
}

async function validateLayer3ReceiptFixture(frame, resolved, fixture) {
  try {
    await navigateFrame(frame, '/kassabonnen')
    await openReceiptDetail(frame, resolved.batchId)
    const detailDoc = getFrameDocument(frame)
    const completeLineId = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolved.completeLineId}"]`)
      ? String(resolved.completeLineId)
      : findReceiptLineIdByLabel(detailDoc, fixture.completeLineLabel)
    const incompleteLineId = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolved.incompleteLineId}"]`)
      ? String(resolved.incompleteLineId)
      : findReceiptLineIdByLabel(detailDoc, fixture.incompleteLineLabel)
    if (!completeLineId || !incompleteLineId) return null
    return {
      batchId: String(resolved.batchId || ''),
      latestBatchId: String(resolved.latestBatchId || resolved.batchId || ''),
      completeLineId,
      incompleteLineId,
    }
  } catch {
    return null
  }
}

async function resolveReceiptFixture(frame, fixture) {
  if (frame.__rezzervLayer3ReceiptFixture) return frame.__rezzervLayer3ReceiptFixture
  if (fixture.batchId && fixture.completeLineId && fixture.incompleteLineId) {
    const resolved = {
      batchId: String(fixture.batchId),
      latestBatchId: String(fixture.latestBatchId || fixture.batchId || ''),
      completeLineId: String(fixture.completeLineId),
      incompleteLineId: String(fixture.incompleteLineId),
    }
    const validated = await validateLayer3ReceiptFixture(frame, resolved, fixture)
    if (validated) {
      persistLayer3ReceiptFixture(validated, fixture)
      frame.__rezzervLayer3ReceiptFixture = validated
      return validated
    }
    const remapped = await resolveReceiptScenarioByLabels(frame, fixture)
    const merged = {
      batchId: String(remapped.batchId),
      latestBatchId: String(remapped.batchId),
      completeLineId: String(remapped.completeLineId),
      incompleteLineId: String(remapped.incompleteLineId),
    }
    persistLayer3ReceiptFixture(merged, fixture)
    frame.__rezzervLayer3ReceiptFixture = merged
    return merged
  }

  const prepared = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
  const resolved = {
    batchId: String(prepared?.batchId || prepared?.batch_id || ''),
    latestBatchId: String(prepared?.latestBatchId || prepared?.latest_batch_id || prepared?.batchId || prepared?.batch_id || ''),
    completeLineId: String(prepared?.completeLineId || prepared?.complete_line_id || ''),
    incompleteLineId: String(prepared?.incompleteLineId || prepared?.incomplete_line_id || ''),
  }
  if (!resolved.batchId || !resolved.completeLineId || !resolved.incompleteLineId) {
    throw new Error('Layer-3 receipt fixture ontbreekt of is incompleet')
  }
  persistLayer3ReceiptFixture(resolved, fixture)
  frame.__rezzervLayer3ReceiptFixture = resolved
  return resolved
}

function doubleClickElement(element) {
  const view = element?.ownerDocument?.defaultView || window
  element.dispatchEvent(new view.MouseEvent('dblclick', { bubbles: true, cancelable: true, view }))
}

function extractIdFromTestId(element, prefix) {
  const value = String(element?.getAttribute('data-testid') || '')
  return value.startsWith(prefix) ? value.slice(prefix.length) : ''
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase().replace(/\s+/g, ' ')
}

function findReceiptLineIdByLabel(detailDoc, label) {
  const normalizedLabel = normalizeText(label)
  if (!normalizedLabel) return null
  const rows = [...detailDoc.querySelectorAll('[data-testid^="receipt-line-"]')]
    .filter((element) => !String(element.getAttribute('data-testid') || '').startsWith('receipt-line-status-'))
  for (const row of rows) {
    if (!normalizeText(row.textContent).includes(normalizedLabel)) continue
    const rowId = extractIdFromTestId(row, 'receipt-line-')
    if (rowId) return rowId
  }
  return null
}

function openReceiptBatchInline(doc, batchId) {
  const row = doc?.querySelector(`[data-testid="receipt-batch-row-${batchId}"]`)
  if (!row) return false
  clickElement(row)
  doubleClickElement(row)
  return true
}

async function resolveReceiptScenarioByLabels(frame, fixture) {
  await navigateFrame(frame, `/kassabonnen?t=${Date.now()}`)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]
    return rows.length ? rows : null
  }, WAIT_TIMEOUT, 'Geen receipt-batch-row-* gevonden')
  const receiptsDoc = getFrameDocument(frame)
  const rows = [...(receiptsDoc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]
  if (!rows.length) throw new Error('Geen receipt-batch-row-* gevonden')

  const preferredRows = [...rows].sort((a, b) => {
    const aText = normalizeText(a.textContent)
    const bText = normalizeText(b.textContent)
    const aScore = (fixture.batchMatchText && aText.includes(normalizeText(fixture.batchMatchText)) ? 0 : 1) + (aText.includes('volledig verwerkt') ? 10 : 0)
    const bScore = (fixture.batchMatchText && bText.includes(normalizeText(fixture.batchMatchText)) ? 0 : 1) + (bText.includes('volledig verwerkt') ? 10 : 0)
    return aScore - bScore
  })

  for (const row of preferredRows) {
    const batchId = extractIdFromTestId(row, 'receipt-batch-row-')
    if (!batchId) continue
    const batchQuery = `?fixtureBatch=${encodeURIComponent(batchId)}&t=${Date.now()}`
    await navigateFrame(frame, `/kassabonnen${batchQuery}`)
    const currentDoc = getFrameDocument(frame)
    if (!openReceiptBatchInline(currentDoc, batchId)) continue
    await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
    const detailDoc = getFrameDocument(frame)
    const completeLineId = fixture.completeLineId ? String(fixture.completeLineId) : findReceiptLineIdByLabel(detailDoc, fixture.completeLineLabel)
    const incompleteLineId = fixture.incompleteLineId ? String(fixture.incompleteLineId) : findReceiptLineIdByLabel(detailDoc, fixture.incompleteLineLabel)
    if (!completeLineId || !incompleteLineId) continue
    return { batchId, completeLineId, incompleteLineId }
  }
  throw new Error('Layer-3 receipt fixture ontbreekt of is incompleet')
}

async function runScenario(name, fn, results) {
  const start = performance.now()
  try {
    await fn()
    results.push({ name, status: 'passed', error: null, durationMs: Math.round(performance.now() - start) })
  } catch (error) {
    results.push({ name, status: 'failed', error: error.message || 'Onbekende fout', durationMs: Math.round(performance.now() - start) })
  }
}

async function login(frame) {
  await navigateFrame(frame, '/login')
  const doc = getFrameDocument(frame)
  await waitForCondition(() => doc?.querySelector('[data-testid="login-page"]'), WAIT_TIMEOUT, 'login-page niet gevonden')
  const email = doc.querySelector('[data-testid="login-email"]')
  const password = doc.querySelector('[data-testid="login-password"]')
  const submit = doc.querySelector('[data-testid="login-submit"]')
  if (!email || !password || !submit) throw new Error('Login testids ontbreken')
  setInputValue(email, 'admin@rezzerv.local')
  setInputValue(password, 'Rezzerv123')
  clickElement(submit)
  await waitForCondition(() => frame.contentWindow?.location?.pathname === '/home', WAIT_TIMEOUT, 'Login leidde niet naar /home')
  await delay(150)
}

function pickByTestIdPrefix(doc, prefix, preferredId = null) {
  if (preferredId) {
    return doc?.querySelector(`[data-testid="${prefix}${preferredId}"]`) || null
  }
  return doc?.querySelector(`[data-testid^="${prefix}"]`) || null
}

async function openInventoryDetail(frame, articleId = null) {
  if (!articleId) throw new Error('Geen fixture-articleId beschikbaar')
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="inventory-page"]'), WAIT_TIMEOUT, 'inventory-page niet gevonden')
  const trigger = await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return pickByTestIdPrefix(doc, 'inventory-row-', articleId)
  }, WAIT_TIMEOUT, `Fixture inventory-row-${articleId} niet gevonden`)
  doubleClickElement(trigger)
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="article-detail-page"]'), WAIT_TIMEOUT, 'article-detail-page niet gevonden')
  await delay(100)
  return getFrameDocument(frame)
}

async function openReceiptDetail(frame, preferredBatchId = null) {
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]
    return rows.length ? rows : null
  }, WAIT_TIMEOUT, 'Geen receipt-batch-row-* gevonden')
  const doc = getFrameDocument(frame)
  let opened = false
  if (preferredBatchId) opened = openReceiptBatchInline(doc, preferredBatchId)
  if (!opened) {
    const row = preferredBatchId
      ? doc?.querySelector(`[data-testid="receipt-batch-row-${preferredBatchId}"]`) || doc?.querySelector('[data-testid^="receipt-batch-row-"]')
      : doc?.querySelector('[data-testid^="receipt-batch-row-"]')
    if (row) {
      clickElement(row)
      doubleClickElement(row)
      opened = true
    }
  }
  if (!opened) {
    const openButton = pickByTestIdPrefix(doc, 'receipt-batch-open-', preferredBatchId) || pickByTestIdPrefix(doc, 'receipt-batch-open-')
    if (!openButton) throw new Error('Geen receipt-batch-row-* of zichtbare openflow gevonden')
    clickElement(openButton)
  }
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
  await delay(100)
  return getFrameDocument(frame)
}

function assertBuildTagVisible(doc) {
  const tag = doc.querySelector('[data-testid="build-tag"]')
  if (!tag) throw new Error('Versielabel ontbreekt')
  const value = String(tag.textContent || '').trim()
  const expected = `Rezzerv v${getRezzervVersionTag()}`
  if (value !== expected) throw new Error(`Versielabel toont onjuiste waarde: ${value || 'leeg'} (verwacht: ${expected})`)
}

function assertNoExitBar(doc) {
  if (doc.querySelector('.rz-exitbar')) throw new Error('Verboden afsluitbalk gevonden op kernscherm')
}

function assertAppShellPage(doc, pageTestId) {
  const page = doc.querySelector(`[data-testid="${pageTestId}"]`)
  if (!page) throw new Error(`${pageTestId} ontbreekt`)
  if (!doc.querySelector('[data-testid="app-header"]')) throw new Error('Header ontbreekt')
  if (!page.closest('.rz-content-inner')) throw new Error(`${pageTestId} staat niet binnen rz-content-inner`)
  assertNoExitBar(doc)
  return page
}

function assertStructure(doc, pageTestId) {
  const page = doc.querySelector(`[data-testid="${pageTestId}"]`)
  if (!page) throw new Error(`${pageTestId} ontbreekt`)
  if (!page.classList.contains('rz-screen')) throw new Error(`${pageTestId} gebruikt geen rz-screen basisstructuur`)
  if (!doc.querySelector('[data-testid="app-header"]')) throw new Error('Header ontbreekt')
  if (!page.querySelector('.rz-content')) throw new Error('rz-content ontbreekt in de pagina-opbouw')
  if (!page.querySelector('.rz-content-inner')) throw new Error('rz-content-inner ontbreekt in de pagina-opbouw')
}

function assertScreenCard(page) {
  if (!page) throw new Error('ScreenCard/Card ontbreekt')
  if (page.matches?.('[data-testid="screen-card"], .rz-card')) return page
  const card = page.querySelector('[data-testid="screen-card"]') || page.querySelector('.rz-card')
  if (!card) throw new Error('ScreenCard/Card ontbreekt')
  return card
}

function assertTabsWithinCard(card) {
  const tabList = card.querySelector('[data-testid="tabs-tablist"]')
  if (!tabList) throw new Error('Tabs ontbreken binnen de kaart')
  const tabs = tabList.querySelectorAll('[role="tab"]')
  if (!tabs.length) throw new Error('Geen tab-knoppen gevonden')
}

function getReceiptLineStatus(detailDoc, lineId) {
  return String(detailDoc?.querySelector(`[data-testid="receipt-line-status-${lineId}"]`)?.textContent || '').trim()
}

function findReceiptRowByStatus(detailDoc, statusKey) {
  const rows = [...(detailDoc?.querySelectorAll('[data-testid^="receipt-line-"]') || [])]
    .filter((element) => {
      const testId = String(element.getAttribute('data-testid') || '')
      return testId.startsWith('receipt-line-') && !testId.startsWith('receipt-line-status-') && element.tagName === 'TR'
    })
  return rows.find((row) => {
    const rowId = extractIdFromTestId(row, 'receipt-line-')
    return rowId && getReceiptLineStatus(detailDoc, rowId) === statusKey
  }) || null
}

async function ensureReceiptFixture(frame, fixture) {
  const resolvedFixture = await resolveReceiptFixture(frame, fixture)
  await navigateFrame(frame, '/kassabonnen')
  await openReceiptDetail(frame, resolvedFixture.batchId)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return doc?.querySelector('[data-testid^="receipt-line-"]')
  }, WAIT_TIMEOUT, 'Geen receipt-line-* gevonden in kassabondetail')

  let detailDoc = getFrameDocument(frame)
  let completeLineId = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolvedFixture.completeLineId}"]`)
    ? String(resolvedFixture.completeLineId)
    : findReceiptLineIdByLabel(detailDoc, fixture.completeLineLabel)
  let incompleteLineId = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolvedFixture.incompleteLineId}"]`)
    ? String(resolvedFixture.incompleteLineId)
    : findReceiptLineIdByLabel(detailDoc, fixture.incompleteLineLabel)

  let completeRow = completeLineId ? detailDoc.querySelector(`[data-testid="receipt-line-${completeLineId}"]`) : null
  let incompleteRow = incompleteLineId ? detailDoc.querySelector(`[data-testid="receipt-line-${incompleteLineId}"]`) : null
  let completeSelect = completeLineId ? detailDoc.querySelector(`[data-testid="receipt-line-select-${completeLineId}"]`) : null
  let incompleteSelect = incompleteLineId ? detailDoc.querySelector(`[data-testid="receipt-line-select-${incompleteLineId}"]`) : null

  if (!completeRow || !incompleteRow || !completeSelect || !incompleteSelect) {
    throw new Error('Layer-3 fixtureregels ontbreken in kassabondetail')
  }

  const incompleteArticle = detailDoc.querySelector(`[data-testid="receipt-line-article-select-${incompleteLineId}"] select`)
  const incompleteLocation = detailDoc.querySelector(`[data-testid="receipt-line-location-select-${incompleteLineId}"]`)
  const completeArticle = detailDoc.querySelector(`[data-testid="receipt-line-article-select-${completeLineId}"] select`)
  const completeLocation = detailDoc.querySelector(`[data-testid="receipt-line-location-select-${completeLineId}"]`)

  if (incompleteArticle) setSelectValue(incompleteArticle, '')
  if (incompleteLocation) setSelectValue(incompleteLocation, '')

  if (completeArticle && !completeArticle.value) {
    const nextArticleValue = [...completeArticle.options].find((option) => option.value)?.value
    if (nextArticleValue) setSelectValue(completeArticle, nextArticleValue)
  }

  if (completeLocation && !completeLocation.value) {
    const nextValue = [...completeLocation.options].find((option) => option.value)?.value
    if (nextValue) setSelectValue(completeLocation, nextValue)
  }

  if (!completeSelect.checked) clickElement(completeSelect)
  if (!incompleteSelect.checked) clickElement(incompleteSelect)

  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const readyRow = findReceiptRowByStatus(doc, 'ready')
    const actionRow = findReceiptRowByStatus(doc, 'action_needed')
    return readyRow && actionRow
  }, WAIT_TIMEOUT, 'Layer-3 fixtureregels ontbreken in kassabondetail')

  detailDoc = getFrameDocument(frame)
  const readyRow = findReceiptRowByStatus(detailDoc, 'ready')
  const actionRow = findReceiptRowByStatus(detailDoc, 'action_needed')
  if (readyRow) {
    completeRow = readyRow
    completeLineId = extractIdFromTestId(readyRow, 'receipt-line-') || completeLineId
  }
  if (actionRow) {
    incompleteRow = actionRow
    incompleteLineId = extractIdFromTestId(actionRow, 'receipt-line-') || incompleteLineId
  }

  const normalizedResolved = {
    batchId: String(resolvedFixture.batchId || ''),
    latestBatchId: String(resolvedFixture.latestBatchId || resolvedFixture.batchId || ''),
    completeLineId: String(completeLineId),
    incompleteLineId: String(incompleteLineId),
  }
  persistLayer3ReceiptFixture(normalizedResolved, fixture)
  frame.__rezzervLayer3ReceiptFixture = normalizedResolved

  await delay(120)
  return { detailDoc, completeRow, incompleteRow }
}

function assertRowColor(row, expectedColor, label) {
  const view = row?.ownerDocument?.defaultView || window
  const firstCell = row?.querySelector('td')
  const rowColor = row ? view.getComputedStyle(row).backgroundColor : ''
  const cellColor = firstCell ? view.getComputedStyle(firstCell).backgroundColor : ''
  const matched = [cellColor, rowColor].includes(expectedColor)
  if (!matched) {
    throw new Error(`${label} heeft kleur ${cellColor || rowColor || 'onbekend'} in plaats van ${expectedColor}`)
  }
}

export async function runLayer3StyleguideTests() {
  const results = []
  const frame = createHiddenFrame()
  const fixture = getLayer1Fixture()

  try {
    await runScenario('L3.1 Voorraad gebruikt basisstructuur en versielabel', async () => {
      await login(frame)
      await navigateFrame(frame, '/voorraad')
      const doc = getFrameDocument(frame)
      assertStructure(doc, 'inventory-page')
      assertBuildTagVisible(doc)
      assertNoExitBar(doc)
      assertScreenCard(doc.querySelector('[data-testid="inventory-page"]'))
      if (!doc.querySelector('[data-testid="inventory-table"]')) throw new Error('Voorraadtabel ontbreekt')
    }, results)

    await runScenario('L3.2 Artikeldetail gebruikt tabs binnen kaart', async () => {
      await navigateFrame(frame, '/voorraad')
      const detailDoc = await openInventoryDetail(frame, fixture.articleId)
      assertBuildTagVisible(detailDoc)
      const page = assertAppShellPage(detailDoc, 'article-detail-page')
      const card = assertScreenCard(page.parentElement)
      assertTabsWithinCard(card)
    }, results)

    await runScenario('L3.3 Kassabonnen-overzicht gebruikt kaart en versielabel', async () => {
      await navigateFrame(frame, '/kassabonnen')
      const doc = getFrameDocument(frame)
      const page = assertAppShellPage(doc, 'receipts-page')
      assertBuildTagVisible(doc)
      const card = assertScreenCard(page)
      if (!card.querySelector('[data-testid="receipts-table"]')) throw new Error('Kassabonnentabel ontbreekt')
    }, results)

    await runScenario('L3.4 Kassabondetail gebruikt tabs binnen kaart', async () => {
      await navigateFrame(frame, '/kassabonnen')
      const doc = await openReceiptDetail(frame, fixture.batchId)
      assertBuildTagVisible(doc)
      const page = assertAppShellPage(doc, 'receipt-detail-page')
      const card = assertScreenCard(page.closest('[data-testid="screen-card"]') || page.parentElement)
      assertTabsWithinCard(card)
    }, results)

    await runScenario('L3.5 Geselecteerde incomplete bonregel toont lichtoranje status', async () => {
      const { incompleteRow } = await ensureReceiptFixture(frame, fixture)
      assertRowColor(incompleteRow, INCOMPLETE_ROW_COLOR, 'Incomplete geselecteerde bonregel')
    }, results)

    await runScenario('L3.6 Geselecteerde complete bonregel toont lichtgroene status', async () => {
      const { completeRow } = await ensureReceiptFixture(frame, fixture)
      assertRowColor(completeRow, READY_ROW_COLOR, 'Complete geselecteerde bonregel')
    }, results)

    await runScenario('L3.7 Kassabondetail toont exportknop binnen kaart', async () => {
      const { detailDoc } = await ensureReceiptFixture(frame, fixture)
      assertBuildTagVisible(detailDoc)
      const page = assertAppShellPage(detailDoc, 'receipt-detail-page')
      const card = assertScreenCard(page.closest('[data-testid="screen-card"]') || page.parentElement)
      const exportButton = card.querySelector('[data-testid="receipt-export-button"]')
      if (!exportButton) throw new Error('receipt-export-button ontbreekt binnen kaart')
      if (exportButton.disabled) throw new Error('receipt-export-button reageert niet op selectie')
    }, results)
  } finally {
    try {
      await fetch('/api/dev/regression/cleanup', { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: '{}' })
    } catch {}
    removeExistingFrame()
  }

  return results
}

