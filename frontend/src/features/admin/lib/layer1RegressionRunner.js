import { getLayer1Fixture } from './layer1RegressionFixture'

const FRAME_ID = 'rezzerv-layer1-runner-frame'
const WAIT_TIMEOUT = 9000
const POLL_INTERVAL = 100

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function waitForCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    function tick() {
      try {
        const result = check()
        if (result) {
          resolve(result)
          return
        }
      } catch {
        // blijf pollen
      }
      if (Date.now() - start >= timeout) {
        reject(new Error(errorMessage))
        return
      }
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
  frame.title = 'Layer 1 regression runner'
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

function nativeClick(element) {
  if (!element) return
  if (typeof element.click === 'function') {
    element.click()
    return
  }
  clickElement(element)
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



async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!response.ok) {
    throw new Error(`${url} gaf status ${response.status}`)
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  return null
}

async function prepareLayer1ReceiptFixture(frame, fixture) {
  if (fixture.batchId && fixture.completeLineId && fixture.incompleteLineId) {
    const resolved = {
      connectionId: String(fixture.connectionId || ''),
      latestBatchId: String(fixture.latestBatchId || fixture.batchId),
      batchId: String(fixture.batchId),
      completeLineId: String(fixture.completeLineId),
      incompleteLineId: String(fixture.incompleteLineId),
    }
    frame.__rezzervLayer1ReceiptFixture = resolved
    return resolved
  }

  try {
    const prepared = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
    const resolved = {
      connectionId: String(prepared?.connectionId || prepared?.connection_id || ''),
      latestBatchId: String(prepared?.latestBatchId || prepared?.latest_batch_id || prepared?.batchId || prepared?.batch_id || ''),
      batchId: String(prepared?.batchId || prepared?.batch_id || ''),
      completeLineId: String(prepared?.completeLineId || prepared?.complete_line_id || ''),
      incompleteLineId: String(prepared?.incompleteLineId || prepared?.incomplete_line_id || ''),
    }
    if (!resolved.batchId || !resolved.completeLineId || !resolved.incompleteLineId) {
      throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
    }
    frame.__rezzervLayer1ReceiptFixture = resolved
    return resolved
  } catch (error) {
    throw new Error('Layer1 receipt fixture kon niet worden voorbereid')
  }
}

async function prepareReceiptExportFixture(frame) {
  if (frame.__rezzervReceiptExportFixture) return frame.__rezzervReceiptExportFixture
  try {
    const prepared = await requestJson('/api/dev/generate-receipt-export-fixture', { method: 'POST', body: '{}' })
    const resolved = {
      connectionId: String(prepared?.connectionId || prepared?.connection_id || ''),
      batchId: String(prepared?.batchId || prepared?.batch_id || ''),
      latestBatchId: String(prepared?.latestBatchId || prepared?.latest_batch_id || prepared?.batchId || prepared?.batch_id || ''),
      exportLineId: String(prepared?.exportLineId || prepared?.export_line_id || ''),
      exportArticleName: String(prepared?.exportArticleName || prepared?.export_article_name || ''),
    }
    if (!resolved.batchId || !resolved.exportLineId) {
      throw new Error('Export fixture ontbreekt of is incompleet')
    }
    frame.__rezzervReceiptExportFixture = resolved
    return resolved
  } catch (error) {
    throw new Error('Export fixture kon niet worden voorbereid')
  }
}

async function prepareStoreConnectionsFixture(frame) {
  if (frame.__rezzervStoreConnectionsFixture) return frame.__rezzervStoreConnectionsFixture
  try {
    const prepared = await requestJson('/api/dev/generate-store-connections-fixture', { method: 'POST', body: '{}' })
    const resolved = {
      householdId: String(prepared?.householdId || prepared?.household_id || '1'),
      linkedProviderCode: String(prepared?.linkedProviderCode || prepared?.linked_provider_code || ''),
      linkedConnectionId: String(prepared?.linkedConnectionId || prepared?.linked_connection_id || ''),
      linkedCardNumber: String(prepared?.linkedCardNumber || prepared?.linked_card_number || ''),
      updatedCardNumber: String(prepared?.updatedCardNumber || prepared?.updated_card_number || ''),
      unlinkedProviderCode: String(prepared?.unlinkedProviderCode || prepared?.unlinked_provider_code || ''),
      createCardNumber: String(prepared?.createCardNumber || prepared?.create_card_number || ''),
    }
    if (!resolved.linkedProviderCode || !resolved.unlinkedProviderCode) {
      throw new Error('Store connections fixture ontbreekt of is incompleet')
    }
    frame.__rezzervStoreConnectionsFixture = resolved
    return resolved
  } catch (error) {
    throw new Error('Store connections fixture kon niet worden voorbereid')
  }
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

async function waitForReceiptLines(detailDocProvider) {
  return waitForCondition(() => {
    const doc = typeof detailDocProvider === 'function' ? detailDocProvider() : detailDocProvider
    if (!doc) return null
    const rows = [...doc.querySelectorAll('[data-testid^="receipt-line-"]')]
      .filter((element) => !String(element.getAttribute('data-testid') || '').startsWith('receipt-line-status-'))
    return rows.length ? rows : null
  }, WAIT_TIMEOUT, 'Geen receipt-line-* gevonden in kassabondetail')
}

function getReceiptLineRow(detailDoc, lineId) {
  return detailDoc.querySelector(`[data-testid="receipt-line-${lineId}"]`)
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

async function resolveReceiptScenarioByLabels(frame, fixture) {
  await navigateFrame(frame, '/kassabonnen')
  const receiptsDoc = getFrameDocument(frame)
  const rows = [...receiptsDoc.querySelectorAll('[data-testid^="receipt-batch-row-"]')]
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
    const openButton = currentDoc?.querySelector(`[data-testid="receipt-batch-open-${batchId}"]`)
    if (!openButton) continue
    clickElement(openButton)
    await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
    const detailDoc = getFrameDocument(frame)
    await waitForReceiptLines(() => getFrameDocument(frame))
    const completeLineId = fixture.completeLineId ? String(fixture.completeLineId) : findReceiptLineIdByLabel(detailDoc, fixture.completeLineLabel)
    const incompleteLineId = fixture.incompleteLineId ? String(fixture.incompleteLineId) : findReceiptLineIdByLabel(detailDoc, fixture.incompleteLineLabel)
    if (!completeLineId || !incompleteLineId) continue
    const completeSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${completeLineId}"]`)
    const incompleteSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${incompleteLineId}"]`)
    if (!completeSelect || !incompleteSelect) continue
    return { batchId, completeLineId, incompleteLineId }
  }
  throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
}

function pickByTestIdPrefix(doc, prefix, preferredId = null) {
  if (preferredId) {
    const exact = doc.querySelector(`[data-testid="${prefix}${preferredId}"]`)
    if (exact) return exact
  }
  return doc.querySelector(`[data-testid^="${prefix}"]`)
}

function extractIdFromTestId(element, prefix) {
  const value = element?.getAttribute('data-testid') || ''
  return value.startsWith(prefix) ? value.slice(prefix.length) : null
}


function openReceiptBatchInline(doc, batchId) {
  const row = doc?.querySelector(`[data-testid="receipt-batch-row-${batchId}"]`)
  if (!row) return false
  clickElement(row)
  doubleClickElement(row)
  return true
}

function getReceiptDetailScope(doc) {
  const detail = doc?.querySelector('[data-testid="receipt-detail-page"]')
  if (!detail) return null
  return detail.closest('.rz-card') || detail
}

function getReceiptExportButton(doc) {
  const scope = getReceiptDetailScope(doc) || doc
  return scope?.querySelector('[data-testid="receipt-export-button"]') || null
}

function getFirstEnabledReceiptLineSelect(detailDoc) {
  return [...detailDoc.querySelectorAll('[data-testid^="receipt-line-select-"]')]
    .find((element) => !element.disabled) || null
}

function getLastDownload(frame) {
  return frame?.contentWindow?.__rezzervLastDownload || null
}

async function openInventoryDetail(frame, articleId = null) {
  const doc = getFrameDocument(frame)
  const trigger = pickByTestIdPrefix(doc, 'inventory-row-', articleId)
  if (!trigger) throw new Error('Geen inventory-row-* gevonden')
  doubleClickElement(trigger)
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="article-detail-page"]'), WAIT_TIMEOUT, 'article-detail-page niet gevonden')
  return getFrameDocument(frame)
}

async function openReceiptDetail(frame, preferredBatchId = null) {
  const existingDetail = getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]')
  if (existingDetail) {
    return getFrameDocument(frame)
  }
  const doc = getFrameDocument(frame)
  let opened = false
  if (preferredBatchId) {
    opened = openReceiptBatchInline(doc, preferredBatchId)
  }
  if (!opened) {
    const row = preferredBatchId
      ? doc.querySelector(`[data-testid="receipt-batch-row-${preferredBatchId}"]`)
      : doc.querySelector('[data-testid^="receipt-batch-row-"]')
    if (row) {
      clickElement(row)
      doubleClickElement(row)
      opened = true
    }
  }
  if (!opened) {
    const openButton = pickByTestIdPrefix(doc, 'receipt-batch-open-', preferredBatchId)
    if (!openButton) throw new Error('Geen receipt-batch-open-* gevonden')
    clickElement(openButton)
  }
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
  return getFrameDocument(frame)
}

async function openReceiptBatchWithSelectableLines(frame, preferredBatchId = null, preferredLineId = null) {
  const fixtureQuery = preferredBatchId ? `?fixtureBatch=${encodeURIComponent(preferredBatchId)}&t=${Date.now()}` : `?t=${Date.now()}`
  await navigateFrame(frame, `/kassabonnen${fixtureQuery}`)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]
    return rows.length ? rows : null
  }, WAIT_TIMEOUT, 'Geen receipt-batch-row-* gevonden')

  const candidateIds = []
  const seen = new Set()
  const doc = getFrameDocument(frame)

  if (preferredBatchId) {
    const preferred = doc?.querySelector(`[data-testid="receipt-batch-row-${preferredBatchId}"]`)
    if (preferred) {
      candidateIds.push(String(preferredBatchId))
      seen.add(String(preferredBatchId))
    }
  }

  for (const row of [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]) {
    const batchId = extractIdFromTestId(row, 'receipt-batch-row-')
    if (!batchId || seen.has(batchId)) continue
    candidateIds.push(batchId)
    seen.add(batchId)
  }

  for (const batchId of candidateIds) {
    const batchQuery = `?fixtureBatch=${encodeURIComponent(batchId)}&t=${Date.now()}`
    await navigateFrame(frame, `/kassabonnen${batchQuery}`)
    const currentDoc = getFrameDocument(frame)
    const opened = openReceiptBatchInline(currentDoc, batchId)
    if (!opened) continue

    const detailDoc = await waitForCondition(() => {
      const liveDoc = getFrameDocument(frame)
      const detail = liveDoc?.querySelector('[data-testid="receipt-detail-page"]')
      if (!detail) return null
      const scope = getReceiptDetailScope(liveDoc) || detail
      if (preferredLineId) {
        const exact = scope.querySelector(`[data-testid="receipt-line-select-${preferredLineId}"]`)
        return exact && !exact.disabled ? liveDoc : null
      }
      const selectable = [...scope.querySelectorAll('[data-testid^="receipt-line-select-"]')]
        .find((element) => !element.disabled)
      return selectable ? liveDoc : null
    }, WAIT_TIMEOUT, preferredLineId ? `Fixtureregel receipt-line-select-${preferredLineId} niet selecteerbaar in batch ${batchId}` : 'Geen batch met selecteerbare receipt-line-select-* gevonden')

    const scope = getReceiptDetailScope(detailDoc) || detailDoc
    const lineSelect = preferredLineId
      ? scope.querySelector(`[data-testid="receipt-line-select-${preferredLineId}"]`)
      : getFirstEnabledReceiptLineSelect(scope)

    if (lineSelect && !lineSelect.disabled) {
      return { detailDoc, lineSelect, batchId }
    }
  }

  const finalDoc = getFrameDocument(frame)
  const rowIds = [...(finalDoc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])].map((el)=>el.getAttribute('data-testid'))
  const openIds = [...(finalDoc?.querySelectorAll('[data-testid^="receipt-batch-open-"]') || [])].map((el)=>el.getAttribute('data-testid'))
  throw new Error(preferredLineId ? `Fixturebatch ${preferredBatchId || 'onbekend'} niet bruikbaar; rowIds=${rowIds.join(',')}; openIds=${openIds.join(',')}; fixtureLine=${preferredLineId}` : 'Geen batch met selecteerbare receipt-line-select-* gevonden')
}

function getReceiptSelectableLineIds(detailDoc) {
  return [...detailDoc.querySelectorAll('[data-testid^="receipt-line-select-"]')]
    .filter((element) => !element.disabled)
    .map((element) => extractIdFromTestId(element, 'receipt-line-select-'))
    .filter(Boolean)
}

function getLineArticleControl(detailDoc, lineId) {
  const articleWrapper = detailDoc.querySelector(`[data-testid="receipt-line-article-select-${lineId}"]`)
  const articleControl = articleWrapper?.querySelector('select') || articleWrapper?.querySelector('input') || null
  return { articleWrapper, articleControl }
}

function getLineLocationControl(detailDoc, lineId) {
  return detailDoc.querySelector(`[data-testid="receipt-line-location-select-${lineId}"]`)
}

function getReceiptLineState(detailDoc, lineId) {
  const lineSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${lineId}"]`)
  const statusNode = detailDoc.querySelector(`[data-testid="receipt-line-status-${lineId}"]`)
  const statusValue = String(statusNode?.textContent || '').trim().toLowerCase()
  const { articleWrapper, articleControl } = getLineArticleControl(detailDoc, lineId)
  const locationControl = getLineLocationControl(detailDoc, lineId)
  const articleValue = articleControl?.value ?? ''
  const locationValue = locationControl?.value ?? ''
  const hasValidArticle = Boolean(articleWrapper) && Boolean(articleValue)
  const hasValidLocation = Boolean(locationControl) && Boolean(locationValue)
  const isIncomplete = !hasValidArticle || !hasValidLocation || (!!statusValue && statusValue !== 'ready')
  return {
    lineId,
    lineSelect,
    statusNode,
    statusValue,
    articleWrapper,
    articleControl,
    locationControl,
    hasValidArticle,
    hasValidLocation,
    isIncomplete,
  }
}

async function resolveReceiptFixture(frame, fixture) {
  if (frame.__rezzervLayer1ReceiptFixture) {
    return frame.__rezzervLayer1ReceiptFixture
  }

  const hasExplicitFixtureIds = Boolean(fixture.batchId && fixture.completeLineId && fixture.incompleteLineId)
  if (hasExplicitFixtureIds) {
    const resolved = {
      connectionId: String(fixture.connectionId || ''),
      latestBatchId: String(fixture.latestBatchId || fixture.batchId),
      batchId: String(fixture.batchId),
      completeLineId: String(fixture.completeLineId),
      incompleteLineId: String(fixture.incompleteLineId),
    }
    frame.__rezzervLayer1ReceiptFixture = resolved
    return resolved
  }

  throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
}

async function login(frame) {
  await navigateFrame(frame, '/login')
  const doc = getFrameDocument(frame)
  const page = await waitForCondition(() => doc?.querySelector('[data-testid="login-page"]'), WAIT_TIMEOUT, 'login-page niet gevonden')
  if (!page) throw new Error('Loginpagina niet gevonden')
  const emailInput = doc.querySelector('[data-testid="login-email"]')
  const passwordInput = doc.querySelector('[data-testid="login-password"]')
  const submitButton = doc.querySelector('[data-testid="login-submit"]')
  if (!emailInput || !passwordInput || !submitButton) {
    throw new Error('Login testids ontbreken')
  }
  setInputValue(emailInput, 'admin@rezzerv.local')
  setInputValue(passwordInput, 'Rezzerv123')
  clickElement(submitButton)
  await waitForCondition(() => frame.contentWindow?.location?.pathname === '/home', WAIT_TIMEOUT, 'Login leidde niet naar /home')
  await delay(150)
}

export async function runLayer1RegressionTests() {
  const results = []
  const frame = createHiddenFrame()
  const fixture = getLayer1Fixture()
  frame.__rezzervLayer1ReceiptFixture = null

  try {
    await runScenario('T1 Login werkt', async () => {
      await login(frame)
      const path = frame.contentWindow?.location?.pathname
      if (path !== '/home') throw new Error(`Verwacht /home na login, kreeg ${path || 'onbekend'}`)
    }, results)

    await runScenario('T2 Voorraad opent', async () => {
      await navigateFrame(frame, '/voorraad')
      const doc = getFrameDocument(frame)
      const page = await waitForCondition(() => doc?.querySelector('[data-testid="inventory-page"]'), WAIT_TIMEOUT, 'inventory-page niet gevonden')
      const table = doc.querySelector('[data-testid="inventory-table"]')
      if (!page || !table) throw new Error('Voorraadpagina of -tabel ontbreekt')
    }, results)

    await runScenario('T3 Artikeldetail opent vanuit Voorraad', async () => {
      await navigateFrame(frame, '/voorraad')
      const detailDoc = await openInventoryDetail(frame, fixture.articleId)
      if (!detailDoc.querySelector('[data-testid="article-detail-title"]')) throw new Error('article-detail-title ontbreekt')
    }, results)

    await runScenario('T4 Kassabonpagina opent', async () => {
      await prepareLayer1ReceiptFixture(frame, fixture)
      await navigateFrame(frame, '/kassabonnen')
      const doc = getFrameDocument(frame)
      if (!doc.querySelector('[data-testid="receipts-page"]')) throw new Error('receipts-page niet gevonden')
      if (!doc.querySelector('[data-testid="receipts-table"]')) throw new Error('receipts-table niet gevonden')
    }, results)

    await runScenario('T5 Kassabondetail opent', async () => {
      const receiptFixture = await resolveReceiptFixture(frame, fixture)
      await navigateFrame(frame, '/kassabonnen')
      const detailDoc = await openReceiptDetail(frame, receiptFixture.batchId)
      if (!detailDoc?.querySelector('[data-testid="receipt-lines-table"]')) throw new Error('receipt-lines-table niet gevonden')
    }, results)

    await runScenario('T6 Complete kassabonregel kan naar voorraad', async () => {
      const receiptFixture = await resolveReceiptFixture(frame, fixture)
      await navigateFrame(frame, '/kassabonnen')
      const detailDoc = await openReceiptDetail(frame, receiptFixture.batchId)
      await waitForReceiptLines(() => getFrameDocument(frame))
      const lineSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${receiptFixture.completeLineId}"]`)
      if (!lineSelect) throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
      const lineId = extractIdFromTestId(lineSelect, 'receipt-line-select-')
      const { articleWrapper, articleControl } = getLineArticleControl(detailDoc, lineId)
      const locationSelect = getLineLocationControl(detailDoc, lineId)
      if (!articleWrapper || !locationSelect) throw new Error(`Artikel- of locatiekeuze ontbreekt voor regel ${lineId}`)
      if (!lineSelect.checked) clickElement(lineSelect)
      if (articleControl?.tagName === 'SELECT') {
        const nextOption = [...articleControl.options].find((option) => option.value)
        if (!nextOption) throw new Error(`Geen artikeloptie beschikbaar voor regel ${lineId}`)
        setSelectValue(articleControl, nextOption.value)
      }
      const nextLocationOption = [...locationSelect.options].find((option) => option.value)
      if (!nextLocationOption) throw new Error(`Geen locatieoptie beschikbaar voor regel ${lineId}`)
      setSelectValue(locationSelect, nextLocationOption.value)
      const processButton = detailDoc.querySelector('[data-testid="receipt-process-button"]')
      if (!processButton) throw new Error('receipt-process-button niet gevonden')
      clickElement(processButton)
      await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-feedback"]'), WAIT_TIMEOUT, 'receipt-feedback niet zichtbaar na verwerken')
    }, results)

    await runScenario('T7 Incomplete kassabonregel wordt geblokkeerd', async () => {
      const receiptFixture = await resolveReceiptFixture(frame, fixture)
      if (!receiptFixture.incompleteLineId) throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
      await navigateFrame(frame, '/kassabonnen')
      const detailDoc = await openReceiptDetail(frame, receiptFixture.batchId)
      await waitForReceiptLines(() => getFrameDocument(frame))
      const lineSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${receiptFixture.incompleteLineId}"]`)
      if (!lineSelect) throw new Error('Layer1 receipt fixture ontbreekt of is incompleet')
      const lineId = extractIdFromTestId(lineSelect, 'receipt-line-select-')
      const stateBefore = getReceiptLineState(detailDoc, lineId)
      if (!stateBefore.isIncomplete) {
        throw new Error(`Fixtureregel ${lineId} is niet onvolledig voor T7`)
      }
      if (!lineSelect.checked) clickElement(lineSelect)
      const processButton = detailDoc.querySelector('[data-testid="receipt-process-button"]')
      if (!processButton) throw new Error('receipt-process-button niet gevonden')
      clickElement(processButton)
      await delay(250)
      const statusNode = detailDoc.querySelector(`[data-testid="receipt-line-status-${lineId}"]`)
      if (!statusNode) throw new Error(`receipt-line-status-${lineId} niet gevonden`)
      const statusValue = String(statusNode.textContent || '').trim().toLowerCase()
      if (!statusValue || statusValue === 'ready') {
        throw new Error(`Regel ${lineId} werd niet als incomplete regel herkend`)
      }
    }, results)

    await runScenario('T8 Huishoudautomatisering uit', async () => {
      await navigateFrame(frame, '/instellingen/huishoudautomatisering')
      const doc = getFrameDocument(frame)
      if (!doc.querySelector('[data-testid="settings-page"]')) throw new Error('settings-page niet gevonden')
      const toggle = doc.querySelector('[data-testid="household-automation-toggle"]')
      const save = doc.querySelector('[data-testid="household-automation-save"]')
      if (!toggle || !save) throw new Error('Automatiseringstoggle of save ontbreekt')
      setSelectValue(toggle, 'none')
      clickElement(save)
      await delay(250)
      if (toggle.value !== 'none') throw new Error('Huishoudautomatisering bleef niet op uit staan')
    }, results)

    await runScenario('T9 Huishoudautomatisering aan/follow', async () => {
      await navigateFrame(frame, '/instellingen/huishoudautomatisering')
      const doc = getFrameDocument(frame)
      const toggle = doc.querySelector('[data-testid="household-automation-toggle"]')
      const save = doc.querySelector('[data-testid="household-automation-save"]')
      if (!toggle || !save) throw new Error('Automatiseringstoggle of save ontbreekt')
      const nextValue = [...toggle.options].find((option) => option.value && option.value !== 'none')?.value
      if (!nextValue) throw new Error('Geen niet-none automatiseringsoptie beschikbaar')
      setSelectValue(toggle, nextValue)
      clickElement(save)
      await delay(250)
      if (toggle.value !== nextValue) throw new Error('Huishoudautomatisering bleef niet op aan/follow staan')
    }, results)

    await runScenario('T10 Historie en Analyse zijn consistent bereikbaar', async () => {
      await navigateFrame(frame, '/voorraad')
      const detailDoc = await openInventoryDetail(frame, fixture.articleId)
      const historyTab = detailDoc.querySelector('[data-testid="article-history-tab"]')
      const analysisTab = detailDoc.querySelector('[data-testid="article-analysis-tab"]')
      if (!historyTab || !analysisTab) throw new Error('Historie- of analyse-tab ontbreekt')
      clickElement(historyTab)
      await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="history-page"]'), WAIT_TIMEOUT, 'history-page niet gevonden')
      clickElement(analysisTab)
      await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="analysis-page"]'), WAIT_TIMEOUT, 'analysis-page niet gevonden')
    }, results)

    await runScenario('T11 Export-testdataset response levert vaste CSV met kolomtitels', async () => {
      const exportFixture = await prepareReceiptExportFixture(frame)
      const targetBatchId = exportFixture.latestBatchId || exportFixture.batchId
      const response = await fetch(`/api/dev/export-receipt-export-fixture?batchId=${encodeURIComponent(targetBatchId)}&lineId=${encodeURIComponent(exportFixture.exportLineId)}`)
      if (!response.ok) throw new Error(`Export-testdataset endpoint gaf status ${response.status}`)
      const contentType = response.headers.get('content-type') || ''
      if (!contentType.toLowerCase().includes('text/csv')) throw new Error('Export-testdataset response is geen CSV')
      const rowCountHeader = response.headers.get('x-rezzerv-row-count') || ''
      const csv = await response.text()
      if (!csv) throw new Error('Export-testdataset CSV ontbreekt')
      const firstLine = String(csv || '').split('\n')[0] || ''
      if (!firstLine.includes('Bonartikel') || !firstLine.includes('Locatie')) throw new Error('Export-testdataset mist kolomtitels')
      if (rowCountHeader && rowCountHeader !== '1') throw new Error('Export-testdataset moet exact 1 regel exporteren')
      const dataLines = String(csv || '').trim().split(/\r?\n/)
      if (dataLines.length !== 2) throw new Error('Export-testdataset moet exact 1 gegevensregel bevatten')
      if (!String(csv || '').includes(exportFixture.exportArticleName)) throw new Error('Export-testdataset mist de vaste testregel')
    }, results)


    await runScenario('T12 Winkelkoppeling kan worden opgeslagen en blijft zichtbaar na refresh', async () => {
      const storeFixture = await prepareStoreConnectionsFixture(frame)
      await navigateFrame(frame, `/winkelkoppelingen?t=${Date.now()}`)
      let doc = getFrameDocument(frame)
      const statusBefore = await waitForCondition(() => doc?.querySelector(`[data-testid="store-connection-status-${storeFixture.unlinkedProviderCode}"]`), WAIT_TIMEOUT, 'Status voor ongekoppelde winkel ontbreekt')
      if (normalizeText(statusBefore.textContent) !== 'niet gekoppeld') throw new Error('Onverwachte beginstatus voor ongekoppelde winkel')
      const action = doc.querySelector(`[data-testid="store-connection-action-${storeFixture.unlinkedProviderCode}"]`)
      if (!action) throw new Error('Koppelactie ontbreekt voor ongekoppelde winkel')
      clickElement(action)
      await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="store-connection-editor"]'), WAIT_TIMEOUT, 'store-connection-editor niet gevonden')
      doc = getFrameDocument(frame)
      const input = doc.querySelector('[data-testid="store-connection-card-number"]')
      const save = doc.querySelector('[data-testid="store-connection-save"]')
      if (!input || !save) throw new Error('Kaartnummerinput of opslaan ontbreekt')
      setInputValue(input, storeFixture.createCardNumber)
      clickElement(save)
      await waitForCondition(() => normalizeText(getFrameDocument(frame)?.querySelector(`[data-testid="store-connection-status-${storeFixture.unlinkedProviderCode}"]`)?.textContent) === 'gekoppeld', WAIT_TIMEOUT, 'Status werd niet gekoppeld na opslaan')
      await navigateFrame(frame, `/winkelkoppelingen?refresh=${Date.now()}`)
      doc = getFrameDocument(frame)
      const statusAfter = await waitForCondition(() => doc?.querySelector(`[data-testid="store-connection-status-${storeFixture.unlinkedProviderCode}"]`), WAIT_TIMEOUT, 'Gekoppelde status ontbreekt na refresh')
      if (normalizeText(statusAfter.textContent) !== 'gekoppeld') throw new Error('Gekoppelde status bleef niet zichtbaar na refresh')
      const refNode = doc.querySelector(`[data-testid="store-connection-ref-${storeFixture.unlinkedProviderCode}"]`)
      if (!refNode || !String(refNode.textContent || '').includes(storeFixture.createCardNumber)) throw new Error('Kaartnummer bleef niet zichtbaar na refresh')
    }, results)

  } finally {
    removeExistingFrame()
  }

  return results
}
