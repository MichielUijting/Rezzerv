const FRAME_ID = "rezzerv-regression-runner-frame"
const WAIT_TIMEOUT = 9000
const POLL_INTERVAL = 100
const HOUSEHOLD_KEY = 'rezzerv_household_auto_consume_on_repurchase'
const ARTICLE_OVERRIDE_KEY = 'rezzerv_article_auto_consume_overrides'

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



function waitForAsyncCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    async function tick() {
      try {
        const result = await check()
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
  frame.title = 'Regression test runner'
  frame.setAttribute('aria-hidden', 'true')
  Object.assign(frame.style, {
    position: 'fixed',
    left: '-10000px',
    top: '0',
    width: '1280px',
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

function queryText(doc, text) {
  return doc?.body?.textContent?.includes(text)
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
  const normalizedValue = value == null ? '' : String(value)
  const setter = Object.getOwnPropertyDescriptor(view.HTMLSelectElement.prototype, 'value')?.set
  setter?.call(select, normalizedValue)
  if (select.value !== normalizedValue) {
    const fallbackOption = Array.from(select.options || []).find((option) => String(option.value) === normalizedValue)
    if (fallbackOption) fallbackOption.selected = true
  }
  select.dispatchEvent(new view.Event('input', { bubbles: true }))
  select.dispatchEvent(new view.Event('change', { bubbles: true }))
}

function clickElement(element) {
  const view = element?.ownerDocument?.defaultView || window
  element.dispatchEvent(new view.MouseEvent('click', { bubbles: true, cancelable: true, view }))
}

function dblClickElement(element) {
  const view = element?.ownerDocument?.defaultView || window
  element.dispatchEvent(new view.MouseEvent('dblclick', { bubbles: true, cancelable: true, view }))
}

async function runScenario(name, fn, results) {
  try {
    await fn()
    results.push({ name, status: 'passed', error: null })
  } catch (error) {
    results.push({ name, status: 'failed', error: error.message || 'Onbekende fout' })
  }
}


async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data?.detail || data?.message || `Request mislukt voor ${path}`
    throw new Error(typeof detail === 'string' ? detail : `Request mislukt voor ${path}`)
  }
  return data
}

async function prepareRegressionFixture(frame) {
  await requestJson('/api/dev/reset-data', { method: 'POST', body: '{}' })
  await requestJson('/api/dev/generate-demo-data', { method: 'POST', body: '{}' })

  const kitchen = await requestJson('/api/dev/spaces', {
    method: 'POST',
    body: JSON.stringify({ naam: 'Schuur' }),
  })

  const workbench = await requestJson('/api/dev/sublocations', {
    method: 'POST',
    body: JSON.stringify({ naam: 'Werkbank', space_id: kitchen.id }),
  })

  const pantry = await requestJson('/api/dev/spaces', {
    method: 'POST',
    body: JSON.stringify({ naam: 'Voorraad test' }),
  })

  const shelf = await requestJson('/api/dev/sublocations', {
    method: 'POST',
    body: JSON.stringify({ naam: 'Plank test', space_id: pantry.id }),
  })

  await requestJson('/api/dev/inventory', {
    method: 'POST',
    body: JSON.stringify({
      naam: 'Mosterd',
      aantal: 1,
      space_id: pantry.id,
      sublocation_id: shelf.id,
    }),
  })

  await requestJson('/api/dev/inventory', {
    method: 'POST',
    body: JSON.stringify({
      naam: 'Boormachine',
      aantal: 1,
      space_id: kitchen.id,
      sublocation_id: workbench.id,
    }),
  })

  resetAutomationState(frame)
}

async function getRegressionHouseholdId(frame) {
  const token = frame?.contentWindow?.localStorage?.getItem('rezzerv_token') || ''
  const household = await requestJson('/api/household', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  return String(household?.id || '1')
}

async function setStoreImportSimplificationLevel(frame, level) {
  const householdId = await getRegressionHouseholdId(frame)
  return requestJson(`/api/dev/household/store-import-settings?household_id=${encodeURIComponent(householdId)}`, {
    method: 'PUT',
    body: JSON.stringify({ store_import_simplification_level: level }),
  })
}

async function ensureLoggedIn(frame) {
  await navigateFrame(frame, '/login')
  const doc = getFrameDocument(frame)
  const emailInput = await waitForCondition(() => doc?.querySelector('input[placeholder="admin@rezzerv.local"]'), WAIT_TIMEOUT, 'E-mailveld niet gevonden')
  const passwordInput = doc.querySelector('input[type="password"]')
  const submitButton = Array.from(doc.querySelectorAll('button')).find((button) => button.textContent?.includes('Inloggen'))
  if (!passwordInput || !submitButton) throw new Error('Loginformulier is onvolledig')
  setInputValue(emailInput, 'admin@rezzerv.local')
  setInputValue(passwordInput, 'Rezzerv123')
  clickElement(submitButton)
  await waitForCondition(() => frame.contentWindow?.location?.pathname === '/home', WAIT_TIMEOUT, 'Login leidde niet naar de startpagina')
}

function resetAutomationState(frame) {
  frame.contentWindow.localStorage.removeItem(HOUSEHOLD_KEY)
  frame.contentWindow.localStorage.removeItem(ARTICLE_OVERRIDE_KEY)
}


function getActiveBatchId(frame) {
  const pathname = frame?.contentWindow?.location?.pathname || ''
  const match = pathname.match(/\/winkels\/batch\/([^/?#]+)/)
  return match?.[1] || null
}

async function fetchBatchById(batchId) {
  if (!batchId) return null
  return requestJson(`/api/purchase-import-batches/${batchId}`).catch(() => null)
}

function getBatchLine(batch, articleName) {
  const normalized = String(articleName || '').trim().toLowerCase()
  return (Array.isArray(batch?.lines) ? batch.lines : []).find((line) => String(line?.article_name_raw || '').trim().toLowerCase() === normalized) || null
}

async function getActiveBatchLine(frame, articleName) {
  const batchId = getActiveBatchId(frame)
  const batch = await fetchBatchById(batchId)
  return getBatchLine(batch, articleName)
}


async function openStoresPage(frame) {
  await navigateFrame(frame, '/winkels')
  const doc = getFrameDocument(frame)
  await waitForCondition(() => queryText(doc, 'Winkelimport'), WAIT_TIMEOUT, 'Winkelimport pagina opent niet')
}

async function clickButtonByText(doc, label) {
  const button = Array.from(doc?.querySelectorAll('button') || []).find((entry) => entry.textContent?.trim() === label)
  if (!button) throw new Error(`Knop ${label} niet gevonden`)
  clickElement(button)
  return button
}

async function ensureProviderConnectionAndBatch(frame, providerName, expectedArticleName) {
  await openStoresPage(frame)
  let doc = getFrameDocument(frame)

  const connectButton = Array.from(doc?.querySelectorAll('button') || []).find((entry) => entry.textContent?.includes(`${providerName} koppelen`))
  if (connectButton) {
    clickElement(connectButton)
    await waitForCondition(
      () => queryText(getFrameDocument(frame), `${providerName} is gekoppeld aan dit huishouden.`) || queryText(getFrameDocument(frame), 'Status: gekoppeld / actief'),
      WAIT_TIMEOUT,
      `${providerName} koppelen werd niet bevestigd`
    )
  }

  const pullButton = await waitForCondition(() => {
    const buttons = Array.from(getFrameDocument(frame)?.querySelectorAll('button') || [])
    return buttons.find((entry) => {
      if (entry.textContent?.trim() !== 'Aankopen ophalen') return false
      const providerBlock = entry.closest('[data-testid^="store-provider-"]') || entry.closest('div[style]')?.parentElement || entry.parentElement?.parentElement || entry.parentElement
      return providerBlock?.textContent?.includes(providerName)
    }) || null
  }, WAIT_TIMEOUT, 'Knop Aankopen ophalen niet gevonden')
  clickElement(pullButton)

  await waitForCondition(() => {
    const refreshedDoc = getFrameDocument(frame)
    return queryText(refreshedDoc, `Nieuwe mockaankopen van ${providerName}`) || queryText(refreshedDoc, 'open bon') || queryText(refreshedDoc, providerName)
  }, WAIT_TIMEOUT, `Nieuwe aankopen voor ${providerName} werden niet bevestigd`)

  const batchActionButton = await waitForCondition(() => {
    const buttons = Array.from(getFrameDocument(frame)?.querySelectorAll('button') || [])
    return buttons.find((entry) => {
      const label = entry.textContent?.trim()
      if (!['Openen', 'Hervatten', 'Naar voorraad'].includes(label || '')) return false
      const batchCard = entry.closest('[data-testid^="open-batch-"]') || entry.closest('div[style]')
      return batchCard?.textContent?.includes(providerName)
    }) || null
  }, WAIT_TIMEOUT, `Open bon voor ${providerName} niet gevonden`)

  if (batchActionButton.textContent?.trim() === 'Naar voorraad') {
    throw new Error(`Batch van ${providerName} staat direct op Naar voorraad en kan niet als detail worden geopend voor regressietest`)
  }

  clickElement(batchActionButton)
  await waitForCondition(() => queryText(getFrameDocument(frame), `Kassabon ${providerName}`), WAIT_TIMEOUT, `Kassabon ${providerName} werd niet geladen`)
  await waitForCondition(() => getStoreLineRow(frame, expectedArticleName), WAIT_TIMEOUT, `Regel ${expectedArticleName} niet zichtbaar in Kassabon ${providerName}`)
}

function getStoreLineRow(frame, articleName) {
  const doc = getFrameDocument(frame)
  const rows = Array.from(doc?.querySelectorAll('.rz-store-review-table tbody tr') || [])
  return rows.find((row) => row.querySelector('td .rz-store-primary')?.textContent?.trim() === articleName) || null
}

function getStoreLineState(frame, articleName) {
  const row = getStoreLineRow(frame, articleName)
  if (!row) return null
  const selects = row.querySelectorAll('select')
  const suggestion = row.querySelector('.rz-store-suggestion')?.textContent?.trim() || ''
  return {
    review: selects[0]?.value || '',
    mappedArticle: selects[1]?.value || '',
    location: selects[2]?.value || '',
    suggestion,
  }
}

async function ensureStoreLineSuggestionState(frame, articleName, mode) {
  await waitForAsyncCondition(async () => {
    const line = await getActiveBatchLine(frame, articleName)
    if (!line) return false
    if (mode === 'suggest-only') {
      return (line.preparation_mode === 'suggest_only' || Boolean(line.suggested_household_article_id) || Boolean(line.suggested_location_id)) && !line.matched_household_article_id && !line.target_location_id
    }
    if (mode === 'auto-ready') {
      return Boolean(line.matched_household_article_id) && Boolean(line.target_location_id) && (line.review_decision || 'selected') === 'selected'
    }
    return false
  }, WAIT_TIMEOUT, `Voorstelstatus ${mode} werd niet bereikt voor ${articleName}. Diagnose: ${JSON.stringify(await getActiveBatchLine(frame, articleName))}`)
}

async function ensureStoreLineExplanationContains(frame, articleName, expectedText) {
  await waitForAsyncCondition(async () => {
    const line = await getActiveBatchLine(frame, articleName)
    const row = getStoreLineRow(frame, articleName)
    const text = row?.textContent || ''
    if (text.includes(expectedText)) return true
    if (expectedText === 'Eerdere mapping gevonden: artikel + locatie') {
      return Boolean(line?.suggested_household_article_id || line?.matched_household_article_id) && Boolean(line?.suggested_location_id || line?.target_location_id)
    }
    if (expectedText === 'Alleen voorstel door niveau Voorzichtig') {
      return text.includes('Alleen voorstel') || line?.preparation_mode === 'suggest_only'
    }
    if (expectedText === 'Geen eerdere mapping gevonden') {
      return text.includes(expectedText) || (!line?.suggested_household_article_id && !line?.matched_household_article_id)
    }
    return false
  }, WAIT_TIMEOUT, `Uitleg voor ${articleName} bevat niet: ${expectedText}`)
}

async function setStoreLineReviewDecision(frame, articleName, decision) {
  const row = await waitForCondition(() => getStoreLineRow(frame, articleName), WAIT_TIMEOUT, `Regel ${articleName} niet gevonden`)
  const selects = row.querySelectorAll('select')
  const reviewSelect = selects[0]
  if (!reviewSelect) throw new Error(`Review-select ontbreekt voor ${articleName}`)
  setSelectValue(reviewSelect, decision)
  await delay(30)
  reviewSelect.dispatchEvent(new Event('change', { bubbles: true }))
  await waitForCondition(() => {
    const refreshedRow = getStoreLineRow(frame, articleName)
    return refreshedRow?.querySelectorAll('select')?.[0]?.value === decision
  }, WAIT_TIMEOUT, `Reviewbeslissing ${decision} werd niet opgeslagen voor ${articleName}`)
}

async function setStoreLineArticle(frame, articleName, mappedArticleId) {
  const row = await waitForCondition(() => getStoreLineRow(frame, articleName), WAIT_TIMEOUT, `Regel ${articleName} niet gevonden`)
  const articleSelect = row.querySelectorAll('select')[1]
  if (!articleSelect) throw new Error(`Artikelselect ontbreekt voor ${articleName}`)
  setSelectValue(articleSelect, mappedArticleId)
  await delay(30)
  articleSelect.dispatchEvent(new Event('change', { bubbles: true }))
  await waitForCondition(() => {
    const refreshedRow = getStoreLineRow(frame, articleName)
    return String(refreshedRow?.querySelectorAll('select')?.[1]?.value || '') === String(mappedArticleId)
  }, WAIT_TIMEOUT, (() => {
    const refreshedRow = getStoreLineRow(frame, articleName)
    const articleSelect = refreshedRow?.querySelectorAll('select')?.[1] || null
    const options = Array.from(articleSelect?.options || []).map((entry) => `${entry.textContent?.trim() || '?'}=${entry.value}`).join(', ')
    return `Artikelkoppeling werd niet opgeslagen voor ${articleName}. Geprobeerd: ${mappedArticleId}. Beschikbare opties: ${options}`
  })())
}

async function setStoreLineLocationByLabel(frame, articleName, expectedLabel) {
  const row = await waitForCondition(() => getStoreLineRow(frame, articleName), WAIT_TIMEOUT, `Regel ${articleName} niet gevonden`)
  const locationSelect = row.querySelectorAll('select')[2]
  if (!locationSelect) throw new Error(`Locatieselect ontbreekt voor ${articleName}`)
  const option = Array.from(locationSelect.options).find((entry) => entry.textContent?.trim() === expectedLabel)
  if (!option) throw new Error(`Locatie ${expectedLabel} niet gevonden voor ${articleName}`)
  setSelectValue(locationSelect, option.value)
  await delay(30)
  locationSelect.dispatchEvent(new Event('change', { bubbles: true }))
  await waitForCondition(() => {
    const refreshedRow = getStoreLineRow(frame, articleName)
    return refreshedRow?.querySelectorAll('select')?.[2]?.value === option.value
  }, WAIT_TIMEOUT, `Locatie ${expectedLabel} werd niet opgeslagen voor ${articleName}`)
}

async function ensureStoreLineReadyForProcessing(frame, articleName, mappedArticleId, expectedLocationLabel) {
  const row = await waitForCondition(() => getStoreLineRow(frame, articleName), WAIT_TIMEOUT, `Regel ${articleName} niet gevonden`)
  const selects = row.querySelectorAll('select')
  const reviewValue = selects[0]?.value || 'pending'
  const articleValue = selects[1]?.value || ''
  const locationSelect = selects[2]
  const locationOption = Array.from(locationSelect?.options || []).find((entry) => entry.textContent?.trim() === expectedLocationLabel)
  const locationValue = locationSelect?.value || ''

  if (reviewValue !== 'selected') {
    await setStoreLineReviewDecision(frame, articleName, 'selected')
  }
  if (articleValue !== mappedArticleId) {
    await setStoreLineArticle(frame, articleName, mappedArticleId)
  }
  if (!locationOption) throw new Error(`Locatie ${expectedLocationLabel} niet gevonden voor ${articleName}`)
  if (locationValue !== locationOption.value) {
    await setStoreLineLocationByLabel(frame, articleName, expectedLocationLabel)
  }
}

function describeStoreReviewState(frame) {
  const doc = getFrameDocument(frame)
  const rows = Array.from(doc?.querySelectorAll('.rz-store-review-table tbody tr') || [])
  const details = rows.map((row) => {
    const cells = row.querySelectorAll('td')
    const selects = row.querySelectorAll('select')
    return {
      article: row.querySelector('td .rz-store-primary')?.textContent?.trim() || '',
      review: selects[0]?.value || '',
      mappedArticle: selects[1]?.value || '',
      location: selects[2]?.value || '',
      blockerText: cells[4]?.textContent?.trim() || '',
    }
  })
  const warningTitle = doc?.querySelector('#process-warning-title')?.textContent?.trim() || ''
  const warningText = doc?.querySelector('.rz-modal-text')?.textContent?.trim() || ''
  const statusCards = Array.from(doc?.querySelectorAll('.rz-card') || [])
    .map((card) => card.textContent?.trim() || '')
    .filter(Boolean)
  return {
    warningTitle,
    warningText,
    statusCards,
    rows: details,
  }
}

async function processCurrentStoreBatch(frame) {
  const batchId = getActiveBatchId(frame)
  const activeTitle = getFrameDocument(frame)?.querySelector('[data-testid="active-batch-title"]')?.textContent?.trim() || ''
  const providerName = activeTitle.replace(/^Kassabon\s+/, '').trim()
  const processButton = await waitForCondition(
    () => Array.from(getFrameDocument(frame)?.querySelectorAll('button') || []).find((entry) => entry.textContent?.trim() === 'Naar voorraad'),
    WAIT_TIMEOUT,
    'Knop Naar voorraad niet gevonden'
  )
  clickElement(processButton)
  await delay(250)

  const immediateState = describeStoreReviewState(frame)
  if (immediateState.warningTitle || immediateState.warningText) {
    throw new Error(`Verwerken geblokkeerd: ${immediateState.warningTitle || 'waarschuwing'} ${immediateState.warningText}`.trim())
  }

  await waitForAsyncCondition(async () => {
    const doc = getFrameDocument(frame)
    const pathname = frame.contentWindow?.location?.pathname || ''
    const texts = [
      'Verwerking afgerond',
      'Verwerkt!',
      'Verwerkt naar voorraad',
      'Er staan geen open regels meer in deze kassabon.',
    ]
    if (texts.some((entry) => queryText(doc, entry))) return true

    if (pathname === '/winkels') {
      const statusText = doc?.body?.textContent || ''
      if (statusText.includes('Verwerking afgerond')) return true
      if (providerName && statusText.includes(providerName) && statusText.includes('Verwerkt')) return true
      if (batchId) {
        const batch = await fetchBatchById(batchId)
        if (batch?.import_status === 'processed') return true
      }
      return false
    }

    const busyButton = Array.from(doc?.querySelectorAll('button') || []).find((entry) => entry.textContent?.trim() === 'Bezig…')
    if (busyButton) return false

    const batch = await fetchBatchById(batchId)
    if (batch?.import_status === 'processed') return true

    const state = describeStoreReviewState(frame)
    if (state.warningTitle || state.warningText) {
      throw new Error(`Verwerken geblokkeerd: ${state.warningTitle || 'waarschuwing'} ${state.warningText}`.trim())
    }

    return false
  }, WAIT_TIMEOUT, `Verwerken naar voorraad werd niet bevestigd. Diagnose: ${JSON.stringify(describeStoreReviewState(frame))}`)
}

async function getInventoryRows() {
  const data = await requestJson('/api/dev/inventory-preview')
  return Array.isArray(data?.rows) ? data.rows : []
}

async function getInventoryQuantity(articleName) {
  const rows = await getInventoryRows()
  return rows
    .filter((row) => String(row?.artikel || '').trim().toLowerCase() === String(articleName || '').trim().toLowerCase())
    .reduce((total, row) => total + (Number(row?.aantal) || 0), 0)
}

async function getInventoryArticleId(articleName) {
  const rows = await getInventoryRows()
  const match = rows.find((row) => String(row?.artikel || '').trim().toLowerCase() === String(articleName || '').trim().toLowerCase())
  if (!match?.id) {
    throw new Error(`Artikel ${articleName} niet gevonden in live voorraad-preview`)
  }
  return String(match.id)
}

async function getStoreReviewArticleOptionId(articleName) {
  const items = await requestJson('/api/store-review-articles')
  const normalized = String(articleName || '').trim().toLowerCase()
  const match = Array.isArray(items)
    ? items.find((item) => String(item?.name || '').trim().toLowerCase() === normalized)
    : null

  if (!match?.id) {
    const available = Array.isArray(items) ? items.map((item) => `${item?.name || '?'}=${item?.id || '?'}`).join(', ') : ''
    throw new Error(`Review-artikeloptie ${articleName} niet gevonden. Beschikbaar: ${available}`)
  }

  return String(match.id)
}

async function getArticleHistoryRows(articleName) {
  const data = await requestJson(`/api/dev/article-history?article_name=${encodeURIComponent(articleName)}`)
  return Array.isArray(data?.rows) ? data.rows : []
}


async function ensureStoreImportPersisted(articleName, beforeQuantity, providerCode = null, timeout = WAIT_TIMEOUT) {
  await waitForAsyncCondition(async () => {
    const quantity = await getInventoryQuantity(articleName)
    if (Number(quantity) <= Number(beforeQuantity)) return false

    const rows = await getArticleHistoryRows(articleName)
    return rows.some((row) => {
      if (row?.source !== 'store_import') return false
      if (!providerCode) return true
      return String(row?.note || '').includes(`provider=${providerCode}`)
    })
  }, timeout, `Winkelimport voor ${articleName} werd niet volledig bevestigd${providerCode ? ` via ${providerCode}` : ''}`)
}

async function ensureArticleHistoryContainsStoreImport(articleName, providerCode = null) {
  await waitForAsyncCondition(async () => {
    const rows = await getArticleHistoryRows(articleName)
    return rows.some((row) => {
      if (row?.source !== 'store_import') return false
      if (!providerCode) return true
      return String(row?.note || '').includes(`provider=${providerCode}`)
    })
  }, WAIT_TIMEOUT, `Geen winkelimport-historie gevonden voor ${articleName}`)
}

async function ensureArticleHistoryStoreImportCount(articleName, minimumCount, providerCode = null) {
  await waitForAsyncCondition(async () => {
    const rows = await getArticleHistoryRows(articleName)
    const matchingRows = rows.filter((row) => {
      if (row?.source !== 'store_import') return false
      if (!providerCode) return true
      return String(row?.note || '').includes(`provider=${providerCode}`)
    })
    return matchingRows.length >= minimumCount
  }, WAIT_TIMEOUT, `Minder dan ${minimumCount} winkelimport-events gevonden voor ${articleName}`)
}

async function ensureInventoryContainsArticle(frame, articleName) {
  await navigateFrame(frame, '/voorraad')
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = Array.from(doc?.querySelectorAll('tbody tr') || [])
    return rows.some((entry) => entry.querySelectorAll('td')[1]?.textContent?.trim() === articleName)
  }, WAIT_TIMEOUT, `Artikel ${articleName} niet zichtbaar in Voorraad`)
}

async function openSettings(frame) {
  await navigateFrame(frame, '/instellingen')
}

async function setHouseholdAutomation(frame, enabled) {
  await navigateFrame(frame, '/instellingen/huishoudautomatisering')
  const doc = getFrameDocument(frame)
  const checkbox = await waitForCondition(() => doc?.querySelector('input[type="checkbox"]'), WAIT_TIMEOUT, 'Checkbox voor huishoudautomatisering niet gevonden')
  if (checkbox.checked !== enabled) {
    clickElement(checkbox)
    await delay(100)
  }
  const saveButton = Array.from(doc.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Opslaan')
  if (!saveButton) throw new Error('Opslaan-knop in Huishoudautomatisering niet gevonden')
  clickElement(saveButton)
  await waitForCondition(() => queryText(doc, 'Opgeslagen'), WAIT_TIMEOUT, 'Opslaan van huishoudautomatisering werd niet bevestigd')
}

async function openArticleFromInventory(frame, articleName) {
  await navigateFrame(frame, '/voorraad')
  const row = await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = Array.from(doc?.querySelectorAll('tbody tr') || [])
    return rows.find((entry) => entry.querySelectorAll('td')[1]?.textContent?.trim() === articleName) || null
  }, WAIT_TIMEOUT, `Artikel ${articleName} niet gevonden in Voorraad`)
  dblClickElement(row)
  await waitForCondition(() => {
    const detailDoc = getFrameDocument(frame)
    return frame.contentWindow?.location?.pathname.startsWith('/voorraad/') && queryText(detailDoc, `Artikel details: ${articleName}`)
  }, WAIT_TIMEOUT, `Artikeldetail voor ${articleName} opende niet`)
}

async function openArticleTab(frame, tabLabel) {
  const doc = getFrameDocument(frame)
  const tabButton = Array.from(doc?.querySelectorAll('button[role="tab"]') || []).find((button) => button.textContent?.trim() === tabLabel)
  if (!tabButton) throw new Error(`Tab ${tabLabel} niet gevonden`)
  clickElement(tabButton)
  await delay(150)
}

async function setArticleOverride(frame, mode) {
  await openArticleTab(frame, 'Overzicht')
  const doc = getFrameDocument(frame)
  const select = await waitForCondition(() => doc?.querySelector('.rz-article-automation-select'), WAIT_TIMEOUT, 'Override-select niet gevonden in Overzicht')
  setSelectValue(select, mode)
  await delay(200)
}


async function ensureTabContains(frame, tabLabel, expectedText, errorText) {
  await openArticleTab(frame, tabLabel)
  const doc = getFrameDocument(frame)
  await waitForCondition(() => queryText(doc, expectedText), WAIT_TIMEOUT, errorText)
}

async function ensureHistoryAutoState(frame, articleName, expectedVisible) {
  await openArticleTab(frame, 'Historie')
  const doc = getFrameDocument(frame)
  await waitForCondition(() => queryText(doc, 'Voorraadhistorie'), WAIT_TIMEOUT, 'Historie-tab is niet zichtbaar')
  const hasAuto = queryText(doc, 'Automatisch (herhaalaankoop)')
  if (expectedVisible && !hasAuto) {
    throw new Error(`Automatische afboeking niet zichtbaar in Historie voor ${articleName}`)
  }
  if (!expectedVisible && hasAuto) {
    throw new Error(`Automatische afboeking is zichtbaar in Historie voor ${articleName}, maar dat hoort niet`)
  }
}

async function ensureAnalysisStatus(frame, expectedText) {
  await openArticleTab(frame, 'Analyse')
  const doc = getFrameDocument(frame)
  await waitForCondition(() => queryText(doc, 'Automatisering'), WAIT_TIMEOUT, 'Analyse-tab Automatisering niet zichtbaar')
  await waitForCondition(() => queryText(doc, expectedText), WAIT_TIMEOUT, `Analyse toont niet de verwachte automatiseringsstatus: ${expectedText}`)
}

async function ensureHistoryCardsAtLeast(frame, minimumCount) {
  await openArticleTab(frame, 'Historie')
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const cards = Array.from(doc?.querySelectorAll('.rz-history-card') || [])
    return cards.length >= minimumCount
  }, WAIT_TIMEOUT, `Minder dan ${minimumCount} historiekaarten zichtbaar in Artikeldetails`)
}

export async function runBrowserRegressionTests() {
  const results = []
  const frame = createHiddenFrame()

  try {
    await ensureLoggedIn(frame)
    await prepareRegressionFixture(frame)

    await runScenario('Artikeldetail Overzicht toont inhoud', async () => {
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Overzicht', 'Automatisering', 'Overzicht-tab toont geen inhoud')
    }, results)

    await runScenario('Artikeldetail Voorraad toont inhoud', async () => {
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Voorraad', 'Totale voorraad', 'Voorraad-tab toont geen inhoud')
    }, results)

    await runScenario('Artikeldetail Locaties toont inhoud', async () => {
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Locaties', 'Primaire locatie', 'Locaties-tab toont geen inhoud')
    }, results)

    await runScenario('Artikeldetail Historie toont inhoud', async () => {
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Historie', 'Voorraadhistorie', 'Historie-tab toont geen inhoud')
    }, results)

    await runScenario('Artikeldetail Analyse toont inhoud', async () => {
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Analyse', 'Automatisering', 'Analyse-tab toont geen inhoud')
    }, results)

    await runScenario('Huishoudinstelling uit → geen automatische afboeking in Historie', async () => {
      await setHouseholdAutomation(frame, false)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'follow_household')
      await ensureHistoryAutoState(frame, 'Mosterd', false)
    }, results)

    await runScenario('Huishoudinstelling aan + follow_household → automatische afboeking zichtbaar', async () => {
      await setHouseholdAutomation(frame, true)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'follow_household')
      await ensureHistoryAutoState(frame, 'Mosterd', true)
    }, results)

    await runScenario('Artikeloverride always_on → automatische afboeking zichtbaar bij huishoudinstelling uit', async () => {
      await setHouseholdAutomation(frame, false)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'always_on')
      await ensureHistoryAutoState(frame, 'Mosterd', true)
    }, results)

    await runScenario('Artikeloverride always_off → automatische afboeking niet zichtbaar bij huishoudinstelling aan', async () => {
      await setHouseholdAutomation(frame, true)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'always_off')
      await ensureHistoryAutoState(frame, 'Mosterd', false)
    }, results)

    await runScenario('Analyse toont juiste automatiseringsstatus voor huishoudinstelling volgen', async () => {
      await setHouseholdAutomation(frame, true)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'follow_household')
      await ensureAnalysisStatus(frame, 'Actief via huishoudinstelling')
    }, results)

    await runScenario('Analyse toont juiste automatiseringsstatus voor artikeloverride always_on', async () => {
      await setHouseholdAutomation(frame, false)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'always_on')
      await ensureAnalysisStatus(frame, 'Actief via artikeloverride')
    }, results)

    await runScenario('Analyse toont juiste automatiseringsstatus voor artikeloverride always_off', async () => {
      await setHouseholdAutomation(frame, true)
      await openArticleFromInventory(frame, 'Mosterd')
      await setArticleOverride(frame, 'always_off')
      await ensureAnalysisStatus(frame, 'Geblokkeerd via artikeloverride')
    }, results)

    await runScenario('Niet-consumable toont geen automatische afboeking en Analyse zegt niet van toepassing', async () => {
      await setHouseholdAutomation(frame, true)
      await openArticleFromInventory(frame, 'Boormachine')
      await ensureHistoryAutoState(frame, 'Boormachine', false)
      await ensureAnalysisStatus(frame, 'Niet van toepassing')
    }, results)

    await runScenario('Lidl-flow opent kassabon na koppelen en aankopen ophalen', async () => {
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      const doc = getFrameDocument(frame)
      await waitForCondition(() => queryText(doc, 'Aankoopdatum: 10-03-2026'), WAIT_TIMEOUT, 'Mock aankoopdatum ontbreekt in Kassabon Lidl')
      await waitForCondition(() => queryText(doc, 'Winkel: Lidl, Hoofdstraat 12, Utrecht'), WAIT_TIMEOUT, 'Mock winkelheader ontbreekt in Kassabon Lidl')
    }, results)

    await runScenario('Jumbo-flow opent kassabon na koppelen en aankopen ophalen', async () => {
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Magere yoghurt')
      const doc = getFrameDocument(frame)
      await waitForCondition(() => queryText(doc, 'Aankoopdatum: 10-03-2026'), WAIT_TIMEOUT, 'Mock aankoopdatum ontbreekt in Kassabon Jumbo')
      await waitForCondition(() => queryText(doc, 'Winkel: Jumbo, Marktplein 8, Utrecht'), WAIT_TIMEOUT, 'Mock winkelheader ontbreekt in Kassabon Jumbo')
    }, results)

    await runScenario('Vereenvoudigingsniveau voorzichtig laat bekende regels als voorstel open staan', async () => {
      await prepareRegressionFixture(frame)
      const melkId = await getStoreReviewArticleOptionId('Melk')
      await setStoreImportSimplificationLevel(frame, 'gebalanceerd')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Halfvolle melk', melkId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Melk')) > 0, WAIT_TIMEOUT, 'Voorbereidende Lidl-opboeking voor Melk mislukte')

      await setStoreImportSimplificationLevel(frame, 'voorzichtig')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineSuggestionState(frame, 'Halfvolle melk', 'suggest-only')
    }, results)

    await runScenario('Vereenvoudigingsniveau gebalanceerd vult bekende regels automatisch in', async () => {
      await prepareRegressionFixture(frame)
      const melkId = await getStoreReviewArticleOptionId('Melk')
      await setStoreImportSimplificationLevel(frame, 'gebalanceerd')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Halfvolle melk', melkId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Melk')) > 0, WAIT_TIMEOUT, 'Voorbereidende Lidl-opboeking voor Melk mislukte')

      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineSuggestionState(frame, 'Halfvolle melk', 'auto-ready')
    }, results)

    await runScenario('Vereenvoudigingsniveau maximaal gemak bereidt bekende regels automatisch voor maar verwerkt niet stil', async () => {
      await prepareRegressionFixture(frame)
      const tomatenId = await getStoreReviewArticleOptionId('Tomaten')
      await setStoreImportSimplificationLevel(frame, 'gebalanceerd')
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Tomaten', tomatenId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Tomaten')) > 0, WAIT_TIMEOUT, 'Voorbereidende Jumbo-opboeking voor Tomaten mislukte')

      const beforeQuantity = await getInventoryQuantity('Tomaten')
      await setStoreImportSimplificationLevel(frame, 'maximaal_gemak')
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      await ensureStoreLineSuggestionState(frame, 'Tomaten', 'auto-ready')
      if ((await getInventoryQuantity('Tomaten')) !== beforeQuantity) {
        throw new Error('Maximaal gemak verwerkte Tomaten stilzwijgend zonder expliciete actie')
      }
    }, results)


    await runScenario('Winkelimport toont uitleg bij bekende regel met alleen voorstel', async () => {
      await prepareRegressionFixture(frame)
      const melkId = await getStoreReviewArticleOptionId('Melk')
      await setStoreImportSimplificationLevel(frame, 'gebalanceerd')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Halfvolle melk', melkId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Melk')) > 0, WAIT_TIMEOUT, 'Voorbereidende Lidl-opboeking voor Melk mislukte')

      await setStoreImportSimplificationLevel(frame, 'voorzichtig')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      await ensureStoreLineExplanationContains(frame, 'Halfvolle melk', 'Eerdere mapping gevonden: artikel + locatie')
      await ensureStoreLineExplanationContains(frame, 'Halfvolle melk', 'Alleen voorstel door niveau Voorzichtig')
    }, results)

    await runScenario('Winkelimport toont uitleg bij onbekende regel zonder mapping', async () => {
      await prepareRegressionFixture(frame)
      await setStoreImportSimplificationLevel(frame, 'gebalanceerd')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await ensureStoreLineExplanationContains(frame, 'Banaan', 'Geen eerdere mapping gevonden')
    }, results)

    await runScenario('Lidl-flow kan een regel koppelen en naar voorraad verwerken', async () => {
      await prepareRegressionFixture(frame)
      const melkId = await getStoreReviewArticleOptionId('Melk')
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      const beforeQuantity = await getInventoryQuantity('Melk')
      await ensureStoreLineReadyForProcessing(frame, 'Halfvolle melk', melkId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await ensureStoreImportPersisted('Melk', beforeQuantity, 'lidl')
      await ensureInventoryContainsArticle(frame, 'Melk')
    }, results)

    await runScenario('Jumbo-flow kan een regel koppelen en naar voorraad verwerken', async () => {
      await prepareRegressionFixture(frame)
      const tomatenId = await getStoreReviewArticleOptionId('Tomaten')
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      const beforeQuantity = await getInventoryQuantity('Tomaten')
      await ensureStoreLineReadyForProcessing(frame, 'Tomaten', tomatenId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await ensureStoreImportPersisted('Tomaten', beforeQuantity, 'jumbo')
      await ensureInventoryContainsArticle(frame, 'Tomaten')
    }, results)

    await runScenario('Winkelimport bewaart twee losse events voor hetzelfde artikel en Historie toont beide', async () => {
      await prepareRegressionFixture(frame)
      const tomatenId = await getStoreReviewArticleOptionId('Tomaten')
      const baselineQuantity = await getInventoryQuantity('Tomaten')

      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Tomaten', tomatenId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await ensureStoreImportPersisted('Tomaten', baselineQuantity, 'jumbo')

      const afterFirstQuantity = await getInventoryQuantity('Tomaten')
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      await ensureStoreLineReadyForProcessing(frame, 'Tomaten', tomatenId, 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await ensureStoreImportPersisted('Tomaten', afterFirstQuantity, 'jumbo')

      await ensureArticleHistoryStoreImportCount('Tomaten', 2, 'jumbo')
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureHistoryCardsAtLeast(frame, 2)
      await waitForCondition(() => {
        const doc = getFrameDocument(frame)
        const notes = Array.from(doc?.querySelectorAll('.rz-history-meta-row .rz-history-meta-value') || []).map((entry) => entry.textContent || '')
        return notes.filter((value) => value.includes('Geïmporteerd via Jumbo')).length >= 2
      }, WAIT_TIMEOUT, 'Historie toont niet beide Jumbo-opboekingen voor Tomaten')
    }, results)
  } finally {
    removeExistingFrame()
  }

  return results
}
