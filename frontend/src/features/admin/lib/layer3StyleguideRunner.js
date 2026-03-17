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

async function requestJson(url, init = {}) {
  const response = await fetch(url, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
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

async function resolveReceiptFixture(frame, fixture) {
  if (frame.__rezzervLayer3ReceiptFixture) return frame.__rezzervLayer3ReceiptFixture
  if (fixture.batchId && fixture.completeLineId && fixture.incompleteLineId) {
    const resolved = {
      batchId: String(fixture.batchId),
      completeLineId: String(fixture.completeLineId),
      incompleteLineId: String(fixture.incompleteLineId),
    }
    frame.__rezzervLayer3ReceiptFixture = resolved
    return resolved
  }

  const prepared = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
  const resolved = {
    batchId: String(prepared?.batchId || prepared?.batch_id || ''),
    completeLineId: String(prepared?.completeLineId || prepared?.complete_line_id || ''),
    incompleteLineId: String(prepared?.incompleteLineId || prepared?.incomplete_line_id || ''),
  }
  if (!resolved.batchId || !resolved.completeLineId || !resolved.incompleteLineId) {
    throw new Error('Layer-3 receipt fixture ontbreekt of is incompleet')
  }
  frame.__rezzervLayer3ReceiptFixture = resolved
  return resolved
}

function doubleClickElement(element) {
  const view = element?.ownerDocument?.defaultView || window
  element.dispatchEvent(new view.MouseEvent('dblclick', { bubbles: true, cancelable: true, view }))
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
    const exact = doc.querySelector(`[data-testid="${prefix}${preferredId}"]`)
    if (exact) return exact
  }
  return doc.querySelector(`[data-testid^="${prefix}"]`)
}

async function openInventoryDetail(frame, articleId = null) {
  const doc = getFrameDocument(frame)
  const trigger = pickByTestIdPrefix(doc, 'inventory-row-', articleId)
  if (!trigger) throw new Error('Geen inventory-row-* gevonden')
  doubleClickElement(trigger)
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="article-detail-page"]'), WAIT_TIMEOUT, 'article-detail-page niet gevonden')
  await delay(100)
  return getFrameDocument(frame)
}

async function openReceiptDetail(frame, preferredBatchId = null) {
  const doc = getFrameDocument(frame)
  const openButton = pickByTestIdPrefix(doc, 'receipt-batch-open-', preferredBatchId)
  if (!openButton) throw new Error('Geen receipt-batch-open-* gevonden')
  clickElement(openButton)
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

async function ensureReceiptFixture(frame, fixture) {
  const resolvedFixture = await resolveReceiptFixture(frame, fixture)
  await navigateFrame(frame, '/kassabonnen')
  await openReceiptDetail(frame, resolvedFixture.batchId)
  const detailDoc = getFrameDocument(frame)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return doc?.querySelector('[data-testid^="receipt-line-"]')
  }, WAIT_TIMEOUT, 'Geen receipt-line-* gevonden in kassabondetail')

  const completeRow = detailDoc.querySelector(`[data-testid="receipt-line-${resolvedFixture.completeLineId}"]`)
  const incompleteRow = detailDoc.querySelector(`[data-testid="receipt-line-${resolvedFixture.incompleteLineId}"]`)
  const completeSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolvedFixture.completeLineId}"]`)
  const incompleteSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${resolvedFixture.incompleteLineId}"]`)

  if (!completeRow || !incompleteRow || !completeSelect || !incompleteSelect) {
    throw new Error('Layer-3 fixtureregels ontbreken in kassabondetail')
  }

  const incompleteArticle = detailDoc.querySelector(`[data-testid="receipt-line-article-select-${resolvedFixture.incompleteLineId}"] select`)
  const incompleteLocation = detailDoc.querySelector(`[data-testid="receipt-line-location-select-${resolvedFixture.incompleteLineId}"]`)
  const completeLocation = detailDoc.querySelector(`[data-testid="receipt-line-location-select-${resolvedFixture.completeLineId}"]`)

  if (incompleteArticle) setSelectValue(incompleteArticle, '')
  if (incompleteLocation) setSelectValue(incompleteLocation, '')

  if (completeLocation && !completeLocation.value) {
    const nextValue = [...completeLocation.options].find((option) => option.value)?.value
    if (nextValue) setSelectValue(completeLocation, nextValue)
  }

  if (!completeSelect.checked) clickElement(completeSelect)
  if (!incompleteSelect.checked) clickElement(incompleteSelect)

  await delay(200)
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
      await navigateFrame(frame, '/kassabonnen')
      const doc = await openReceiptDetail(frame, fixture.batchId)
      assertBuildTagVisible(doc)
      const page = assertAppShellPage(doc, 'receipt-detail-page')
      const card = assertScreenCard(page.closest('[data-testid="screen-card"]') || page.parentElement)
      const exportButton = card.querySelector('[data-testid="receipt-export-button"]')
      if (!exportButton) throw new Error('receipt-export-button ontbreekt binnen kaart')
      const lineSelect = doc.querySelector('[data-testid^="receipt-line-select-"]')
      if (!lineSelect) throw new Error('receipt-line-select-* ontbreekt voor exportstatus')
      if (!exportButton.disabled) throw new Error('receipt-export-button moet starten zonder selectie')
      clickElement(lineSelect)
      await delay(120)
      if (exportButton.disabled) throw new Error('receipt-export-button reageert niet op selectie')
    }, results)
  } finally {
    removeExistingFrame()
  }

  return results
}
