const FRAME_ID = "rezzerv-regression-runner-frame"
const WAIT_TIMEOUT = 8000
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
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function setSelectValue(select, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set
  setter?.call(select, value)
  select.dispatchEvent(new Event('input', { bubbles: true }))
  select.dispatchEvent(new Event('change', { bubbles: true }))
}

function clickElement(element) {
  element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
}

function dblClickElement(element) {
  element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window }))
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


async function openStoresPage(frame) {
  await navigateFrame(frame, '/winkels')
  const doc = getFrameDocument(frame)
  await waitForCondition(() => queryText(doc, 'Winkelkoppelingen'), WAIT_TIMEOUT, 'Winkelkoppelingen pagina opent niet')
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
      () => queryText(getFrameDocument(frame), `${providerName} is gekoppeld aan dit huishouden.`) || queryText(getFrameDocument(frame), 'Koppeling: gekoppeld'),
      WAIT_TIMEOUT,
      `${providerName} koppelen werd niet bevestigd`
    )
  }

  doc = getFrameDocument(frame)
  const pullButton = await waitForCondition(() => {
    const buttons = Array.from(getFrameDocument(frame)?.querySelectorAll('button') || [])
    return buttons.find((entry) => {
      if (entry.textContent?.trim() !== 'Aankopen ophalen') return false
      const providerBlock = entry.closest('div[style]')?.parentElement || entry.parentElement?.parentElement || entry.parentElement
      return providerBlock?.textContent?.includes(providerName)
    }) || null
  }, WAIT_TIMEOUT, 'Knop Aankopen ophalen niet gevonden')
  clickElement(pullButton)
  await waitForCondition(() => queryText(getFrameDocument(frame), `Kassabon ${providerName}`), WAIT_TIMEOUT, `Kassabon ${providerName} werd niet geladen`)
  await waitForCondition(() => getStoreLineRow(frame, expectedArticleName), WAIT_TIMEOUT, `Regel ${expectedArticleName} niet zichtbaar in Kassabon ${providerName}`)
}

function getStoreLineRow(frame, articleName) {
  const doc = getFrameDocument(frame)
  const rows = Array.from(doc?.querySelectorAll('.rz-store-review-table tbody tr') || [])
  return rows.find((row) => row.querySelector('td .rz-store-primary')?.textContent?.trim() === articleName) || null
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
    return refreshedRow?.querySelectorAll('select')?.[1]?.value === mappedArticleId
  }, WAIT_TIMEOUT, `Artikelkoppeling werd niet opgeslagen voor ${articleName}`)
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

async function processCurrentStoreBatch(frame) {
  const processButton = await waitForCondition(
    () => Array.from(getFrameDocument(frame)?.querySelectorAll('button') || []).find((entry) => entry.textContent?.trim() === 'Naar voorraad'),
    WAIT_TIMEOUT,
    'Knop Naar voorraad niet gevonden'
  )
  clickElement(processButton)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    return queryText(doc, 'Verwerkt naar voorraad') || queryText(doc, 'Er staan geen open regels meer in deze kassabon.')
  }, WAIT_TIMEOUT, 'Verwerken naar voorraad werd niet bevestigd')
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

async function getArticleHistoryRows(articleName) {
  const data = await requestJson(`/api/dev/article-history?article_name=${encodeURIComponent(articleName)}`)
  return Array.isArray(data?.rows) ? data.rows : []
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
  const doc = getFrameDocument(frame)
  const rows = Array.from(doc?.querySelectorAll('tbody tr') || [])
  const row = rows.find((entry) => entry.querySelectorAll('td')[1]?.textContent?.trim() === articleName)
  if (!row) throw new Error(`Artikel ${articleName} niet gevonden in Voorraad`)
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

    await runScenario('Lidl-flow kan een regel koppelen en naar voorraad verwerken', async () => {
      await ensureProviderConnectionAndBatch(frame, 'Lidl', 'Halfvolle melk')
      await setStoreLineReviewDecision(frame, 'Banaan', 'ignored')
      await setStoreLineReviewDecision(frame, 'Volkoren pasta', 'ignored')
      await setStoreLineReviewDecision(frame, 'Tomatenblokjes', 'ignored')
      const beforeQuantity = await getInventoryQuantity('Melk')
      await ensureStoreLineReadyForProcessing(frame, 'Halfvolle melk', '4', 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Melk')) > beforeQuantity, WAIT_TIMEOUT, 'Melk werd niet opgeboekt in Voorraad')
      await ensureArticleHistoryContainsStoreImport('Melk', 'lidl')
      await openArticleFromInventory(frame, 'Melk')
      await ensureTabContains(frame, 'Locaties', 'Primaire locatie', 'Locaties-tab toont geen inhoud voor Melk')
      await ensureTabContains(frame, 'Historie', 'Voorraadhistorie', 'Historie-tab toont geen inhoud voor Melk')
    }, results)

    await runScenario('Jumbo-flow kan een regel koppelen en naar voorraad verwerken', async () => {
      await ensureProviderConnectionAndBatch(frame, 'Jumbo', 'Tomaten')
      await setStoreLineReviewDecision(frame, 'Magere yoghurt', 'ignored')
      await setStoreLineReviewDecision(frame, 'Appelsap', 'ignored')
      await setStoreLineReviewDecision(frame, 'Pindakaas', 'ignored')
      const beforeQuantity = await getInventoryQuantity('Tomaten')
      await ensureStoreLineReadyForProcessing(frame, 'Tomaten', '1', 'Voorraad test / Plank test')
      await processCurrentStoreBatch(frame)
      await waitForAsyncCondition(async () => (await getInventoryQuantity('Tomaten')) > beforeQuantity, WAIT_TIMEOUT, 'Tomaten werden niet opgeboekt in Voorraad via Jumbo')
      await ensureArticleHistoryContainsStoreImport('Tomaten', 'jumbo')
      await openArticleFromInventory(frame, 'Tomaten')
      await ensureTabContains(frame, 'Locaties', 'Primaire locatie', 'Locaties-tab toont geen inhoud voor Tomaten')
      await ensureTabContains(frame, 'Historie', 'Voorraadhistorie', 'Historie-tab toont geen inhoud voor Tomaten')
    }, results)
  } finally {
    removeExistingFrame()
  }

  return results
}
