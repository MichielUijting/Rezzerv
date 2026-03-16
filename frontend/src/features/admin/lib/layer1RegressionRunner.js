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
  const openButton = pickByTestIdPrefix(doc, 'receipt-batch-open-', preferredBatchId)
  if (!openButton) throw new Error('Geen receipt-batch-open-* gevonden')
  clickElement(openButton)
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
  return getFrameDocument(frame)
}

async function openReceiptBatchWithSelectableLines(frame, preferredBatchId = null) {
  let detailDoc = getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]') ? getFrameDocument(frame) : null
  if (!detailDoc) {
    detailDoc = await openReceiptDetail(frame, preferredBatchId)
  }
  let lineSelect = detailDoc.querySelector('[data-testid^="receipt-line-select-"]')
  if (lineSelect) {
    return { detailDoc, lineSelect, batchId: preferredBatchId ? String(preferredBatchId) : null }
  }

  await navigateFrame(frame, '/kassabonnen')

  const candidateIds = []
  const seen = new Set()

  function collectCandidateIds(doc) {
    if (!doc) return
    if (preferredBatchId && !seen.has(String(preferredBatchId))) {
      const preferred = doc.querySelector(`[data-testid="receipt-batch-open-${preferredBatchId}"]`)
      if (preferred) {
        candidateIds.push(String(preferredBatchId))
        seen.add(String(preferredBatchId))
      }
    }
    for (const element of [...doc.querySelectorAll('[data-testid^="receipt-batch-open-"]')]) {
      const batchId = extractIdFromTestId(element, 'receipt-batch-open-')
      if (!batchId || seen.has(batchId)) continue
      candidateIds.push(batchId)
      seen.add(batchId)
    }
  }

  collectCandidateIds(getFrameDocument(frame))

  for (const batchId of candidateIds) {
    const currentDoc = getFrameDocument(frame)
    const openButton = currentDoc?.querySelector(`[data-testid="receipt-batch-open-${batchId}"]`)
    if (!openButton) {
      await navigateFrame(frame, '/kassabonnen')
      const refreshedDoc = getFrameDocument(frame)
      const refreshedButton = refreshedDoc?.querySelector(`[data-testid="receipt-batch-open-${batchId}"]`)
      if (!refreshedButton) {
        continue
      }
      clickElement(refreshedButton)
    } else {
      clickElement(openButton)
    }
    await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden')
    detailDoc = getFrameDocument(frame)
    lineSelect = detailDoc.querySelector('[data-testid^="receipt-line-select-"]')
    if (lineSelect) {
      return { detailDoc, lineSelect, batchId }
    }
    await navigateFrame(frame, '/kassabonnen')
  }
  throw new Error('Geen batch met selecteerbare receipt-line-select-* gevonden')
}

function getReceiptSelectableLineIds(detailDoc) {
  return [...detailDoc.querySelectorAll('[data-testid^="receipt-line-select-"]')]
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

  await navigateFrame(frame, '/kassabonnen')
  const opened = await openReceiptBatchWithSelectableLines(frame, fixture.batchId)
  const detailDoc = opened.detailDoc
  const selectableLineIds = getReceiptSelectableLineIds(detailDoc)
  if (!selectableLineIds.length) {
    throw new Error('Geen selecteerbare bonregels gevonden in fixturebatch')
  }

  const lineStates = selectableLineIds.map((lineId) => getReceiptLineState(detailDoc, lineId))
  const completeLine = (fixture.completeLineId && lineStates.find((state) => state.lineId === String(fixture.completeLineId)))
    || lineStates.find((state) => state.hasValidArticle && state.hasValidLocation)
    || lineStates[0]
  const incompleteLine = (fixture.incompleteLineId && lineStates.find((state) => state.lineId === String(fixture.incompleteLineId)))
    || lineStates.find((state) => state.isIncomplete)
    || null

  frame.__rezzervLayer1ReceiptFixture = {
    batchId: fixture.batchId ? String(fixture.batchId) : (opened.batchId ? String(opened.batchId) : null),
    completeLineId: completeLine?.lineId || null,
    incompleteLineId: incompleteLine?.lineId || null,
  }
  return frame.__rezzervLayer1ReceiptFixture
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
      await navigateFrame(frame, '/kassabonnen')
      const doc = getFrameDocument(frame)
      if (!doc.querySelector('[data-testid="receipts-page"]')) throw new Error('receipts-page niet gevonden')
      if (!doc.querySelector('[data-testid="receipts-table"]')) throw new Error('receipts-table niet gevonden')
    }, results)

    await runScenario('T5 Kassabondetail opent', async () => {
      await navigateFrame(frame, '/kassabonnen')
      const detailDoc = await openReceiptDetail(frame, fixture.batchId)
      if (!detailDoc?.querySelector('[data-testid="receipt-lines-table"]')) throw new Error('receipt-lines-table niet gevonden')
    }, results)

    await runScenario('T6 Complete kassabonregel kan naar voorraad', async () => {
      const receiptFixture = await resolveReceiptFixture(frame, fixture)
      await navigateFrame(frame, '/kassabonnen')
      const { detailDoc, lineSelect: fallbackLineSelect } = await openReceiptBatchWithSelectableLines(frame, receiptFixture.batchId)
      const lineSelect = pickByTestIdPrefix(detailDoc, 'receipt-line-select-', receiptFixture.completeLineId) || fallbackLineSelect
      if (!lineSelect) throw new Error('Geen receipt-line-select-* gevonden voor complete test')
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
      if (!receiptFixture.incompleteLineId) throw new Error('Geen fixture incompleteLineId gevonden voor T7')
      await navigateFrame(frame, '/kassabonnen')
      const { detailDoc } = await openReceiptBatchWithSelectableLines(frame, receiptFixture.batchId)
      const lineSelect = pickByTestIdPrefix(detailDoc, 'receipt-line-select-', receiptFixture.incompleteLineId)
      if (!lineSelect) throw new Error('Geen receipt-line-select-* gevonden voor incomplete test')
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
  } finally {
    removeExistingFrame()
  }

  return results
}
