import { getLayer1Fixture } from './layer1RegressionFixture'

const FRAME_ID = 'rezzerv-layer2-runner-frame'
const WAIT_TIMEOUT = 15000
const MANUAL_IMPORT_TIMEOUT = 45000
const POLL_INTERVAL = 100

function delay(ms) { return new Promise((resolve) => window.setTimeout(resolve, ms)) }
function waitForCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    function tick() {
      try { const result = check(); if (result) return resolve(result) } catch {}
      if (Date.now() - start >= timeout) return reject(new Error(errorMessage))
      window.setTimeout(tick, POLL_INTERVAL)
    }
    tick()
  })
}
function waitForAsyncCondition(check, timeout = WAIT_TIMEOUT, errorMessage = 'Timeout') {
  const start = Date.now()
  return new Promise((resolve, reject) => {
    async function tick() {
      try { const result = await check(); if (result) return resolve(result) } catch {}
      if (Date.now() - start >= timeout) return reject(new Error(errorMessage))
      window.setTimeout(tick, POLL_INTERVAL)
    }
    tick()
  })
}
function removeExistingFrame() { const existing=document.getElementById(FRAME_ID); if (existing) existing.remove() }
function createHiddenFrame() { removeExistingFrame(); const frame=document.createElement('iframe'); frame.id=FRAME_ID; frame.title='Layer 2 regression runner'; frame.setAttribute('aria-hidden','true'); Object.assign(frame.style,{position:'fixed',left:'-10000px',top:'0',width:'1440px',height:'900px',opacity:'0',pointerEvents:'none',border:'0',background:'#fff'}); document.body.appendChild(frame); return frame }
function getFrameDocument(frame) { return frame.contentDocument || frame.contentWindow?.document || null }
async function navigateFrame(frame, path) {
  await new Promise((resolve,reject)=>{ let settled=false; const timer=window.setTimeout(()=>{ if(settled)return; settled=true; reject(new Error(`Navigatie naar ${path} duurde te lang`)) }, WAIT_TIMEOUT); function handleLoad(){ if(settled)return; settled=true; window.clearTimeout(timer); resolve() } frame.addEventListener('load', handleLoad, { once:true }); frame.src=path })
  await waitForCondition(()=>{ const doc=getFrameDocument(frame); return doc && doc.readyState==='complete' }, WAIT_TIMEOUT, `Pagina ${path} werd niet volledig geladen`)
  await delay(150)
}
function setInputValue(input, value) { const view=input?.ownerDocument?.defaultView||window; const setter=Object.getOwnPropertyDescriptor(view.HTMLInputElement.prototype,'value')?.set; setter?.call(input, value); input.dispatchEvent(new view.Event('input',{bubbles:true})); input.dispatchEvent(new view.Event('change',{bubbles:true})) }
function setSelectValue(select, value) { const view=select?.ownerDocument?.defaultView||window; const setter=Object.getOwnPropertyDescriptor(view.HTMLSelectElement.prototype,'value')?.set; setter?.call(select, value); select.dispatchEvent(new view.Event('input',{bubbles:true})); select.dispatchEvent(new view.Event('change',{bubbles:true})) }
function clickElement(element) { const view=element?.ownerDocument?.defaultView||window; element.dispatchEvent(new view.MouseEvent('click',{bubbles:true,cancelable:true,view})) }
function nativeClick(element) { if(!element) return; if(typeof element.click==='function'){ element.click(); return } clickElement(element) }
function doubleClickElement(element) { const view=element?.ownerDocument?.defaultView||window; element.dispatchEvent(new view.MouseEvent('dblclick',{bubbles:true,cancelable:true,view})) }
async function runScenario(name, fn, results) { const start=performance.now(); try { await fn(); results.push({name,status:'passed',error:null,durationMs:Math.round(performance.now()-start)}) } catch (error) { results.push({name,status:'failed',error:error.message||'Onbekende fout',durationMs:Math.round(performance.now()-start)}) } }
async function login(frame) { await navigateFrame(frame,'/login'); const doc=getFrameDocument(frame); await waitForCondition(()=>doc?.querySelector('[data-testid="login-page"]'), WAIT_TIMEOUT, 'login-page niet gevonden'); const email=doc.querySelector('[data-testid="login-email"]'); const password=doc.querySelector('[data-testid="login-password"]'); const submit=doc.querySelector('[data-testid="login-submit"]'); if(!email||!password||!submit) throw new Error('Login testids ontbreken'); setInputValue(email,'admin@rezzerv.local'); setInputValue(password,'Rezzerv123'); clickElement(submit); await waitForCondition(()=>frame.contentWindow?.location?.pathname==='/home', WAIT_TIMEOUT, 'Login leidde niet naar /home'); await delay(150) }
function pickByTestIdPrefix(doc, prefix, preferredId = null) { if (preferredId) { const exact = doc.querySelector(`[data-testid="${prefix}${preferredId}"]`); if (exact) return exact } return doc.querySelector(`[data-testid^="${prefix}"]`) }

function openReceiptBatchInline(doc, batchId) { const row=doc?.querySelector(`[data-testid="receipt-batch-row-${batchId}"]`); if(!row) return false; clickElement(row); doubleClickElement(row); return true }
function getReceiptDetailScope(doc) { const detail=doc?.querySelector('[data-testid="receipt-detail-page"]'); if(!detail) return null; return detail.closest('.rz-card') || detail }
function getReceiptExportButton(doc) { const scope=getReceiptDetailScope(doc) || doc; return scope?.querySelector('[data-testid="receipt-export-button"]') || null }
function getFirstEnabledReceiptLineSelect(detailDoc) { return [...(detailDoc?.querySelectorAll('[data-testid^="receipt-line-select-"]') || [])].find((element)=>!element.disabled) || null }
async function openInventoryDetail(frame, articleId = null) { const doc=getFrameDocument(frame); const trigger=pickByTestIdPrefix(doc,'inventory-row-',articleId); if(!trigger) throw new Error('Geen inventory-row-* gevonden'); doubleClickElement(trigger); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="article-detail-page"]'), WAIT_TIMEOUT, 'article-detail-page niet gevonden'); return getFrameDocument(frame) }
async function openReceiptDetail(frame, preferredBatchId = null) { const doc=getFrameDocument(frame); let opened=false; if(preferredBatchId) opened=openReceiptBatchInline(doc, preferredBatchId); if(!opened){ const row=preferredBatchId?doc?.querySelector(`[data-testid="receipt-batch-row-${preferredBatchId}"]`):doc?.querySelector('[data-testid^="receipt-batch-row-"]'); if(row){ clickElement(row); doubleClickElement(row); opened=true } } if(!opened){ const openButton=pickByTestIdPrefix(doc,'receipt-batch-open-',preferredBatchId); if(!openButton) throw new Error('Geen receipt-batch-open-* gevonden'); clickElement(openButton) } await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]'), WAIT_TIMEOUT, 'receipt-detail-page niet gevonden'); return getFrameDocument(frame) }
function getLastDownload(frame) { return frame?.contentWindow?.__rezzervLastDownload || null }
function getRegressionAuthHeaders() {
  try {
    const token = window.localStorage.getItem('rezzerv_token') || ''
    return token ? { Authorization: `Bearer ${token}` } : {}
  } catch {
    return {}
  }
}

async function requestJson(path, init = {}) {
  const response = await fetch(path, {
    method: init.method || 'GET',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...getRegressionAuthHeaders(), ...(init.headers || {}) },
    body: init.body,
  })
  if (!response.ok) throw new Error(`Request naar ${path} mislukte met status ${response.status}`)
  return response.json()
}
function queryButtonByText(doc, label) { return [...(doc?.querySelectorAll('button') || [])].find((entry) => entry.textContent?.trim() === label) || null }
function buildRegressionReceiptEmailToken() { return `regressie-bon-${Date.now()}` }
function buildRegressionReceiptEmailText(token) {
  return [
    'From: Rezzerv Test <regressie@rezzerv.local>',
    `Subject: Rezzerv regressie ${token}`,
    'Date: Sat, 21 Mar 2026 12:34:00 +0100',
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=utf-8',
    'Content-Transfer-Encoding: 8bit',
    '',
    `Lidl kassabon ${token}`,
    'Kassabon',
    'Datum 21-03-2026 12:34',
    `${token} Mosterd 2,49`,
    'Totaal 2,49',
    '',
  ].join('\r\n')
}
function createRegressionReceiptEmailFile(frame, token) {
  const view = frame?.contentWindow || window
  return new view.File([buildRegressionReceiptEmailText(token)], `${token}.eml`, { type: 'message/rfc822' })
}
function dispatchFileDrop(frame, target, file) {
  const view = frame?.contentWindow || window
  const dataTransfer = new view.DataTransfer()
  dataTransfer.items.add(file)
  for (const type of ['dragenter', 'dragover', 'drop']) {
    const event = new view.Event(type, { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
    target.dispatchEvent(event)
  }
}
async function resetRegressionState() {
  await requestJson('/api/dev/regression/reset', { method: 'POST', body: '{}' })
}

async function fetchKassaReceiptItems(householdId = '1') {
  const data = await requestJson(`/api/receipts?householdId=${encodeURIComponent(householdId)}`)
  return Array.isArray(data?.items) ? data.items : []
}
async function openKassaEmailSourceHub(frame) {
  await navigateFrame(frame,'/kassa')
  await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="kassa-page"]'), WAIT_TIMEOUT, 'kassa-page niet gevonden')
  const doc=getFrameDocument(frame)
  const addButton=doc.querySelector('[data-testid="kassa-add-receipt-button"]') || queryButtonByText(doc, 'Bon toevoegen')
  if(!addButton) throw new Error('Bon toevoegen knop niet gevonden')
  clickElement(addButton)
  await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="kassa-email-dropzone"]'), WAIT_TIMEOUT, 'kassa-email-dropzone niet gevonden')
  return getFrameDocument(frame)
}
async function importEmailReceiptViaDropzone(frame, token) {
  const beforeItems = await fetchKassaReceiptItems('1')
  const beforeIds = new Set(beforeItems.map((item) => String(item?.receipt_table_id || '')))
  await openKassaEmailSourceHub(frame)
  const dropzone = await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="kassa-email-dropzone"]'), WAIT_TIMEOUT, 'kassa-email-dropzone niet gevonden')
  const file = createRegressionReceiptEmailFile(frame, token)
  dispatchFileDrop(frame, dropzone, file)
  const importedReceipt = await waitForAsyncCondition(async () => {
    const items = await fetchKassaReceiptItems('1')
    return items.find((item) => !beforeIds.has(String(item?.receipt_table_id || ''))) || null
  }, WAIT_TIMEOUT, 'Nieuwe e-mailbon werd niet toegevoegd aan de inbox')
  await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="kassa-row-${importedReceipt.receipt_table_id}"]`), WAIT_TIMEOUT, 'Nieuwe bonrij is niet zichtbaar in Kassa')
  frame.__rezzervKassaReceiptFixture = { token, receiptTableId: String(importedReceipt.receipt_table_id), householdId: '1' }
  return { beforeItems, importedReceipt }
}
async function triggerDuplicateEmailReceiptViaDropzone(frame, token, expectedReceiptId) {
  const beforeItems = await fetchKassaReceiptItems('1')
  await openKassaEmailSourceHub(frame)
  const dropzone = await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="kassa-email-dropzone"]'), WAIT_TIMEOUT, 'kassa-email-dropzone niet gevonden')
  const file = createRegressionReceiptEmailFile(frame, token)
  dispatchFileDrop(frame, dropzone, file)
  const duplicateFeedback = await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const element = doc?.querySelector('[data-testid="receipt-sourcehub-duplicate-feedback"]')
    return element && element.textContent?.includes('al eerder toegevoegd') ? element : null
  }, WAIT_TIMEOUT, 'Dubbele kassabonmelding werd niet zichtbaar')
  const afterItems = await fetchKassaReceiptItems('1')
  if (afterItems.length !== beforeItems.length) throw new Error('Duplicate import veranderde het aantal bonnen in de inbox')
  if (expectedReceiptId && !afterItems.some((item) => String(item?.receipt_table_id || '') === String(expectedReceiptId))) throw new Error('Oorspronkelijke bon ontbreekt na duplicate import')
  return duplicateFeedback
}
async function deleteReceiptViaKassa(frame, receiptTableId) {
  await navigateFrame(frame,'/kassa')
  const row = await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="kassa-row-${receiptTableId}"]`) || null, WAIT_TIMEOUT, `kassa-row-${receiptTableId} niet gevonden`)
  const checkbox = row.querySelector('input[type="checkbox"]')
  if (!checkbox) throw new Error('Selectiecheckbox voor bon ontbreekt')
  nativeClick(checkbox)
  const deleteButton = getFrameDocument(frame)?.querySelector('[data-testid="kassa-delete-selected-button"]') || queryButtonByText(getFrameDocument(frame), 'Verwijderen')
  if (!deleteButton) throw new Error('Verwijderen-knop niet gevonden')
  if (deleteButton.disabled) throw new Error('Verwijderen-knop bleef uitgeschakeld na selectie')
  clickElement(deleteButton)
  await waitForCondition(() => !getFrameDocument(frame)?.querySelector(`[data-testid="kassa-row-${receiptTableId}"]`), WAIT_TIMEOUT, 'Verwijderde bon bleef zichtbaar in Kassa')
  const items = await fetchKassaReceiptItems('1')
  if (items.some((item) => String(item?.receipt_table_id || '') === String(receiptTableId))) throw new Error('Verwijderde bon bleef aanwezig in de backendlijst')
}
async function buildRegressionFixtureFile(frame, kind) {
  const response = await fetch(`/api/dev/regression/receipt-fixture-file?kind=${encodeURIComponent(kind)}`, { credentials: 'same-origin' })
  if (!response.ok) throw new Error(`Regressie-fixture ${kind} kon niet worden geladen`)
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const fileNameMatch = disposition.match(/filename="?([^";]+)"?/i)
  const fileName = fileNameMatch?.[1] || `regression-${kind}`
  const view = frame?.contentWindow || window
  return new view.File([blob], fileName, { type: blob.type || response.headers.get('content-type') || 'application/octet-stream' })
}
function assignFilesToInput(frame, input, files) {
  const view = input?.ownerDocument?.defaultView || frame?.contentWindow || window
  const dataTransfer = new view.DataTransfer()
  files.forEach((file) => dataTransfer.items.add(file))
  Object.defineProperty(input, 'files', { configurable: true, get: () => dataTransfer.files })
  input.dispatchEvent(new view.Event('change', { bubbles: true }))
}
async function waitForReceiptRowAndDetail(frame, receiptId, errorMessage) {
  await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="kassa-row-${receiptId}"]`) || null, WAIT_TIMEOUT, errorMessage || 'Nieuwe bonrij werd niet zichtbaar in Kassa')
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]') || null, WAIT_TIMEOUT, 'Kassabondetail werd niet automatisch geopend')
}
async function importManualReceiptViaFileInput(frame) {
  await resetRegressionState()
  const beforeItems = await fetchKassaReceiptItems('1')
  const beforeIds = new Set(beforeItems.map((item) => String(item?.receipt_table_id || '')))
  await openKassaEmailSourceHub(frame)
  const input = await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="kassa-manual-file-input"]') || null, WAIT_TIMEOUT, 'Handmatig bestandsinputveld niet gevonden')
  const file = await buildRegressionFixtureFile(frame, 'manual')
  assignFilesToInput(frame, input, [file])
  const importedReceipt = await waitForAsyncCondition(async () => {
    const items = await fetchKassaReceiptItems('1')
    return items.find((item) => !beforeIds.has(String(item?.receipt_table_id || ''))) || null
  }, MANUAL_IMPORT_TIMEOUT, 'Handmatige bestandsimport leverde geen nieuwe bon op')
  await waitForReceiptRowAndDetail(frame, importedReceipt.receipt_table_id, 'Handmatig geïmporteerde bon werd niet zichtbaar in Kassa')
  return importedReceipt
}
async function importCameraReceiptViaFileInput(frame) {
  await resetRegressionState()
  const beforeItems = await fetchKassaReceiptItems('1')
  const beforeIds = new Set(beforeItems.map((item) => String(item?.receipt_table_id || '')))
  await openKassaEmailSourceHub(frame)
  const input = await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="kassa-camera-file-input"]') || null, WAIT_TIMEOUT, 'Camera-inputveld niet gevonden')
  const file = await buildRegressionFixtureFile(frame, 'camera')
  assignFilesToInput(frame, input, [file])
  await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="kassa-camera-modal"]') || null, WAIT_TIMEOUT, 'Camera-controlemodal werd niet geopend')
  const confirmButton = getFrameDocument(frame)?.querySelector('[data-testid="kassa-camera-confirm"]')
  if (!confirmButton) throw new Error('Camera-bevestigingsknop ontbreekt')
  clickElement(confirmButton)
  const importedReceipt = await waitForAsyncCondition(async () => {
    const items = await fetchKassaReceiptItems('1')
    return items.find((item) => !beforeIds.has(String(item?.receipt_table_id || ''))) || null
  }, WAIT_TIMEOUT, 'Camera-import leverde geen nieuwe bon op')
  await waitForReceiptRowAndDetail(frame, importedReceipt.receipt_table_id, 'Camera-geïmporteerde bon werd niet zichtbaar in Kassa')
  return importedReceipt
}
async function importShareReceiptViaApi(frame) {
  await resetRegressionState()
  const beforeItems = await fetchKassaReceiptItems('1')
  const beforeIds = new Set(beforeItems.map((item) => String(item?.receipt_table_id || '')))
  const file = await buildRegressionFixtureFile(frame, 'share')
  const view = frame?.contentWindow || window
  const formData = new view.FormData()
  formData.append('household_id', '1')
  formData.append('source_context', 'shared_app')
  formData.append('source_label', 'Gedeelde regressietest')
  formData.append('file', file, file.name)
  const response = await fetch('/api/receipts/share-import', { method: 'POST', credentials: 'same-origin', body: formData })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || 'Share-import mislukte')
  const importedReceipt = await waitForAsyncCondition(async () => {
    const items = await fetchKassaReceiptItems('1')
    return items.find((item) => !beforeIds.has(String(item?.receipt_table_id || ''))) || null
  }, WAIT_TIMEOUT, 'Share-import leverde geen nieuwe bon op')
  const parseStatus = encodeURIComponent(String(payload?.parse_status || importedReceipt?.parse_status || 'partial'))
  const duplicateFlag = payload?.duplicate ? '1' : '0'
  await navigateFrame(frame, `/kassa?share_status=success&receipt_table_id=${encodeURIComponent(String(importedReceipt?.receipt_table_id || ''))}&duplicate=${duplicateFlag}&parse_status=${parseStatus}`)
  await waitForReceiptRowAndDetail(frame, importedReceipt.receipt_table_id, 'Share-import bon werd niet zichtbaar in Kassa')
  return importedReceipt
}
async function seedRegressionKassaReceipts() {
  return requestJson('/api/dev/regression/seed-kassa-receipts', { method: 'POST', body: '{}' })
}
async function fetchUnpackStartBatches(householdId = '1') {
  const payload = await requestJson(`/api/unpack-start-batches?householdId=${encodeURIComponent(householdId)}`)
  return Array.isArray(payload?.items) ? payload.items : []
}
function getReceiptBatchRow(doc, batchId) {
  return doc?.querySelector(`[data-testid="receipt-batch-row-${batchId}"]`) || null
}
function getBatchStatusCell(row) {
  return row?.querySelectorAll('td')?.[4] || null
}
async function fetchInventoryPreviewRows() {
  const payload = await requestJson('/api/dev/inventory-preview')
  return Array.isArray(payload?.rows) ? payload.rows : []
}
async function getInventoryQuantityByArticleName(articleName) {
  const rows = await fetchInventoryPreviewRows()
  const row = rows.find((entry) => String(entry?.artikel || '').trim().toLowerCase() === String(articleName || '').trim().toLowerCase())
  return Number(row?.aantal || 0)
}
async function getArticleHistoryRows(articleName) {
  const payload = await requestJson(`/api/dev/article-history?article_name=${encodeURIComponent(articleName)}`)
  return Array.isArray(payload?.rows) ? payload.rows : []
}
async function fetchStoreReviewArticleOptions() {
  const payload = await requestJson('/api/store-review-articles')
  return Array.isArray(payload) ? payload : []
}
async function fetchStoreLocationOptions() {
  const household = await requestJson('/api/household')
  const payload = await requestJson(`/api/store-location-options?householdId=${encodeURIComponent(household?.id || '1')}`)
  return Array.isArray(payload) ? payload : []
}
function findArticleOptionId(options, articleName) {
  const target = String(articleName || '').trim().toLowerCase()
  const exact = options.find((entry) => String(entry?.name || '').trim().toLowerCase() === target)
  if (exact?.id) return String(exact.id)
  const partial = options.find((entry) => String(entry?.name || '').trim().toLowerCase().includes(target))
  return partial?.id ? String(partial.id) : ''
}
function findLocationOptionId(options, preferredMatch = 'keuken') {
  const exact = options.find((entry) => String(entry?.label || '').trim().toLowerCase().includes(String(preferredMatch || '').trim().toLowerCase()))
  if (exact?.id) return String(exact.id)
  return options?.[0]?.id ? String(options[0].id) : ''
}
async function mapReceiptBatchLineAndProcess(frame, batchId, articleName) {
  await navigateFrame(frame, '/kassabonnen')
  await openReceiptDetail(frame, batchId)
  const batchBefore = await requestJson(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
  const targetLine = (batchBefore?.lines || []).find((line) => String(line?.processing_status || 'pending') !== 'processed')
  if (!targetLine?.id) throw new Error(`Geen open bonregel gevonden voor batch ${batchId}`)
  const articleOptions = await fetchStoreReviewArticleOptions()
  const articleId = findArticleOptionId(articleOptions, articleName)
  if (!articleId) throw new Error(`Geen artikeloptie gevonden voor ${articleName}`)
  const locationOptions = await fetchStoreLocationOptions()
  const locationId = findLocationOptionId(locationOptions, 'keuken')
  if (!locationId) throw new Error('Geen locatieoptie gevonden voor regressietest')
  const lineSelect = await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="receipt-line-select-${targetLine.id}"]`) || null, WAIT_TIMEOUT, 'Selectiecheckbox voor kassabonregel niet gevonden')
  if (!lineSelect.checked) nativeClick(lineSelect)
  const articleSelect = await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="receipt-line-article-select-${targetLine.id}"] select`) || getFrameDocument(frame)?.querySelector(`[data-testid="receipt-line-article-select-${targetLine.id}"] [data-store-article-select="true"]`) || null, WAIT_TIMEOUT, 'Artikelselector voor kassabonregel niet gevonden')
  setSelectValue(articleSelect, articleId)
  await waitForAsyncCondition(async () => {
    const refreshed = await requestJson(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
    const line = (refreshed?.lines || []).find((entry) => String(entry?.id || '') === String(targetLine.id))
    return String(line?.matched_household_article_id || '') === String(articleId)
  }, WAIT_TIMEOUT, 'Artikelkoppeling werd niet opgeslagen')
  const locationSelect = await waitForCondition(() => getFrameDocument(frame)?.querySelector(`[data-testid="receipt-line-location-select-${targetLine.id}"]`) || null, WAIT_TIMEOUT, 'Locatieselector voor kassabonregel niet gevonden')
  setSelectValue(locationSelect, locationId)
  await waitForAsyncCondition(async () => {
    const refreshed = await requestJson(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
    const line = (refreshed?.lines || []).find((entry) => String(entry?.id || '') === String(targetLine.id))
    return String(line?.target_location_id || '') === String(locationId)
  }, WAIT_TIMEOUT, 'Locatiekoppeling werd niet opgeslagen')
  const processButton = await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-process-button"]') || null, WAIT_TIMEOUT, 'Naar-voorraadknop niet gevonden')
  const beforeQuantity = await getInventoryQuantityByArticleName(articleName)
  clickElement(processButton)
  await waitForAsyncCondition(async () => {
    const refreshed = await requestJson(`/api/purchase-import-batches/${encodeURIComponent(batchId)}`)
    const line = (refreshed?.lines || []).find((entry) => String(entry?.id || '') === String(targetLine.id))
    return String(line?.processing_status || '') === 'processed'
  }, WAIT_TIMEOUT, 'Bonregel werd niet als verwerkt gemarkeerd')
  const afterQuantity = await getInventoryQuantityByArticleName(articleName)
  const historyRows = await waitForAsyncCondition(async () => {
    const rows = await getArticleHistoryRows(articleName)
    const matching = rows.find((entry) => String(entry?.event_type || '') === 'purchase' && String(entry?.note || '').includes(`batch=${batchId}`))
    return matching ? rows : null
  }, WAIT_TIMEOUT, 'Historie bevat geen purchase-event voor de verwerkte kassabonregel')
  return { targetLineId: String(targetLine.id), articleId, locationId, beforeQuantity, afterQuantity, historyRows }
}
async function prepareLayer2ReceiptFixture(frame, fixture) {
  if (frame.__rezzervLayer2ReceiptFixture) return frame.__rezzervLayer2ReceiptFixture
  if (fixture.batchId && fixture.completeLineId) {
    const resolved = { connectionId: String(fixture.connectionId || ''), latestBatchId: String(fixture.latestBatchId || fixture.batchId || ''), batchId: String(fixture.batchId), completeLineId: String(fixture.completeLineId), incompleteLineId: String(fixture.incompleteLineId || '') }
    frame.__rezzervLayer2ReceiptFixture = resolved
    return resolved
  }
  const prepared = await requestJson('/api/dev/generate-layer1-receipt-fixture', { method: 'POST', body: '{}' })
  const resolved = {
    connectionId: String(prepared?.connectionId || prepared?.connection_id || ''),
    latestBatchId: String(prepared?.latestBatchId || prepared?.latest_batch_id || prepared?.batchId || prepared?.batch_id || ''),
    batchId: String(prepared?.batchId || prepared?.batch_id || ''),
    completeLineId: String(prepared?.completeLineId || prepared?.complete_line_id || ''),
    incompleteLineId: String(prepared?.incompleteLineId || prepared?.incomplete_line_id || ''),
  }
  if (!resolved.batchId || !resolved.completeLineId) throw new Error('Layer2 receipt fixture ontbreekt of is incompleet')
  frame.__rezzervLayer2ReceiptFixture = resolved
  return resolved
}

async function prepareReceiptExportFixture(frame) {
  if (frame.__rezzervReceiptExportFixture) return frame.__rezzervReceiptExportFixture
  const prepared = await requestJson('/api/dev/generate-receipt-export-fixture', { method: 'POST', body: '{}' })
  const resolved = {
    connectionId: String(prepared?.connectionId || prepared?.connection_id || ''),
    batchId: String(prepared?.batchId || prepared?.batch_id || ''),
    latestBatchId: String(prepared?.latestBatchId || prepared?.latest_batch_id || prepared?.batchId || prepared?.batch_id || ''),
    exportLineId: String(prepared?.exportLineId || prepared?.export_line_id || ''),
    exportArticleName: String(prepared?.exportArticleName || prepared?.export_article_name || ''),
  }
  if (!resolved.batchId || !resolved.exportLineId) throw new Error('Export fixture ontbreekt of is incompleet')
  frame.__rezzervReceiptExportFixture = resolved
  return resolved
}

async function openReceiptDetailWithSelectableLines(frame, preferredBatchId = null, preferredLineId = null) {
  const fixtureQuery = preferredBatchId ? `?fixtureBatch=${encodeURIComponent(preferredBatchId)}&t=${Date.now()}` : `?t=${Date.now()}`
  await navigateFrame(frame, `/kassabonnen${fixtureQuery}`)
  await waitForCondition(() => {
    const doc = getFrameDocument(frame)
    const rows = [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]
    return rows.length ? rows : null
  }, WAIT_TIMEOUT, 'Geen receipt-batch-row-* gevonden')
  const seen = new Set()
  const candidateIds = []
  const doc = getFrameDocument(frame)
  if (preferredBatchId && doc?.querySelector(`[data-testid="receipt-batch-row-${preferredBatchId}"]`)) {
    candidateIds.push(String(preferredBatchId))
    seen.add(String(preferredBatchId))
  }
  for (const row of [...(doc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]) {
    const id = String(row.getAttribute('data-testid') || '').replace('receipt-batch-row-','')
    if (!id || seen.has(id)) continue
    candidateIds.push(id)
    seen.add(id)
  }
  for (const batchId of candidateIds) {
    const batchQuery = `?fixtureBatch=${encodeURIComponent(batchId)}&t=${Date.now()}`
    await navigateFrame(frame, `/kassabonnen${batchQuery}`)
    const currentDoc = getFrameDocument(frame)
    if (!openReceiptBatchInline(currentDoc, batchId)) continue
    const detailDoc = await waitForCondition(()=>{
      const liveDoc = getFrameDocument(frame)
      const detail = liveDoc?.querySelector('[data-testid="receipt-detail-page"]')
      if (!detail) return null
      const scope = getReceiptDetailScope(liveDoc) || detail
      if (preferredLineId) {
        const exact = scope.querySelector(`[data-testid="receipt-line-select-${preferredLineId}"]`)
        return exact && !exact.disabled ? liveDoc : null
      }
      const lineSelect = [...scope.querySelectorAll('[data-testid^="receipt-line-select-"]')].find((el)=>!el.disabled)
      return lineSelect ? liveDoc : null
    }, WAIT_TIMEOUT, preferredLineId ? `receipt-line-select-${preferredLineId} niet selecteerbaar in batch ${batchId}` : 'Kassabondetailselectie of export ontbreekt')
    const scope = getReceiptDetailScope(detailDoc) || detailDoc
    const lineSelect = preferredLineId
      ? scope.querySelector(`[data-testid="receipt-line-select-${preferredLineId}"]`)
      : getFirstEnabledReceiptLineSelect(scope)
    if (lineSelect && !lineSelect.disabled) return { detailDoc, lineSelect, batchId }
  }
  const finalDoc = getFrameDocument(frame)
  const rowIds = [...(finalDoc?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])].map((el)=>el.getAttribute('data-testid'))
  const openIds = [...(finalDoc?.querySelectorAll('[data-testid^="receipt-batch-open-"]') || [])].map((el)=>el.getAttribute('data-testid'))
  throw new Error(preferredLineId ? `Fixturebatch ${preferredBatchId || 'onbekend'} niet bruikbaar; rowIds=${rowIds.join(',')}; openIds=${openIds.join(',')}; fixtureLine=${preferredLineId}` : 'Kassabondetailselectie of export ontbreekt')
}

export async function runLayer2RouteTests() {
  const results=[]; const frame=createHiddenFrame(); const fixture=getLayer1Fixture(); frame.__rezzervLayer2ReceiptFixture = null;
  try {
    await resetRegressionState()
    await runScenario('R1 Admin opent', async ()=>{ await login(frame); await navigateFrame(frame,'/admin'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="admin-page"]')) throw new Error('admin-page niet gevonden') }, results)
    await runScenario('R2 Winkelimport opent', async ()=>{ await navigateFrame(frame,'/instellingen/winkelimport'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="store-import-page"]')) throw new Error('store-import-page niet gevonden') }, results)
    await runScenario('R3 Instellingenpagina opent', async ()=>{ await navigateFrame(frame,'/instellingen'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="settings-page"]')) throw new Error('settings-page niet gevonden') }, results)
    await runScenario('R4 Artikeldetail tabs zijn bereikbaar', async ()=>{ await navigateFrame(frame,'/voorraad'); const detailDoc=await openInventoryDetail(frame, fixture.articleId); const historyTab=detailDoc.querySelector('[data-testid="article-history-tab"]'); const analysisTab=detailDoc.querySelector('[data-testid="article-analysis-tab"]'); if(!historyTab||!analysisTab) throw new Error('Historie- of analyse-tab ontbreekt') }, results)
    await runScenario('R5 Kassabon-overzicht en detailnavigatie werkt', async ()=>{ await navigateFrame(frame,'/kassabonnen'); let doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="receipts-page"]')) throw new Error('receipts-page niet gevonden'); await openReceiptDetail(frame, fixture.batchId); doc=getFrameDocument(frame); const back=doc.querySelector('[data-testid="receipt-back-to-overview"]'); if(!back) throw new Error('receipt-back-to-overview niet gevonden'); clickElement(back); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="receipts-page"]'), WAIT_TIMEOUT, 'Terug naar kassabonoverzicht lukte niet') }, results)
    await runScenario('R6 Kernnavigatie tussen hoofdschermen werkt', async ()=>{ await navigateFrame(frame,'/voorraad'); if(!getFrameDocument(frame)?.querySelector('[data-testid="inventory-page"]')) throw new Error('inventory-page niet gevonden'); await openInventoryDetail(frame, fixture.articleId); let doc=getFrameDocument(frame); clickElement(doc.querySelector('[data-testid="article-history-tab"]')); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="history-page"]'), WAIT_TIMEOUT, 'history-page niet gevonden'); doc=getFrameDocument(frame); clickElement(doc.querySelector('[data-testid="article-analysis-tab"]')); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="analysis-page"]'), WAIT_TIMEOUT, 'analysis-page niet gevonden'); await navigateFrame(frame,'/kassabonnen'); if(!getFrameDocument(frame)?.querySelector('[data-testid="receipts-page"]')) throw new Error('receipts-page niet gevonden'); await navigateFrame(frame,'/admin'); if(!getFrameDocument(frame)?.querySelector('[data-testid="admin-page"]')) throw new Error('admin-page niet gevonden') }, results)
    await runScenario('R7 Relevante waarschuwingen en modals openen', async ()=>{ await navigateFrame(frame,'/instellingen/winkelimport'); let doc=getFrameDocument(frame); const page=doc.querySelector('[data-testid="store-import-page"]'); if(!page) throw new Error('store-import-page niet gevonden'); const select=doc.querySelector('[data-testid="store-import-level-select"]'); if(!select) throw new Error('store-import-level-select niet gevonden'); const current=select.value; const next=[...select.options].find(o=>o.value && o.value!==current)?.value; if(!next) throw new Error('Geen alternatieve winkelimportoptie beschikbaar'); setSelectValue(select, next); const backLink=doc.querySelector('[data-testid="store-import-back-link"]'); if(!backLink) throw new Error('store-import-back-link niet gevonden'); clickElement(backLink); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="warning-dialog"]'), WAIT_TIMEOUT, 'warning-dialog niet gevonden'); const cancel=getFrameDocument(frame).querySelector('[data-testid="warning-cancel"]'); if(!cancel) throw new Error('warning-cancel niet gevonden'); clickElement(cancel); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="store-import-page"]'), WAIT_TIMEOUT, 'Terugkeer naar winkelimport na annuleren mislukte') }, results)
    await runScenario('R8 Admin regressie-overzicht en testpaneel opent', async ()=>{ await navigateFrame(frame,'/admin'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="test-run-panel"]')) throw new Error('test-run-panel niet gevonden'); if(!doc.querySelector('[data-testid="test-status-card"]')) throw new Error('test-status-card niet gevonden') }, results)
    await runScenario('R9 Runtime diagnose dropdown-locaties blijft bereikbaar via admin', async ()=>{ await navigateFrame(frame,'/admin'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="admin-runtime-diagnostics-panel"]')) throw new Error('admin-runtime-diagnostics-panel niet gevonden'); if(!doc.querySelector('[data-testid="admin-diagnostic-location-button"]')) throw new Error('admin-diagnostic-location-button niet gevonden') }, results)
    await runScenario('R10 Runtime diagnose verwerkvalidatie blijft bereikbaar via admin', async ()=>{ await navigateFrame(frame,'/admin'); const doc=getFrameDocument(frame); if(!doc.querySelector('[data-testid="admin-runtime-diagnostics-panel"]')) throw new Error('admin-runtime-diagnostics-panel niet gevonden'); if(!doc.querySelector('[data-testid="admin-diagnostic-process-button"]')) throw new Error('admin-diagnostic-process-button niet gevonden') }, results)
    await runScenario('R11 Voorraad → Artikeldetail → Archiveren → Voorraad werkt', async ()=>{ await navigateFrame(frame,'/voorraad'); const inventoryDoc=getFrameDocument(frame); const trigger=inventoryDoc.querySelector('[data-testid^="inventory-row-"]'); if(!trigger) throw new Error('Geen inventory-row-* gevonden'); const articleId=String(trigger.getAttribute('data-testid')||'').replace('inventory-row-',''); doubleClickElement(trigger); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="article-detail-page"]'), WAIT_TIMEOUT, 'article-detail-page niet gevonden'); const detailDoc=getFrameDocument(frame); const archiveButton=detailDoc.querySelector('[data-testid="article-archive-button"]'); if(!archiveButton) throw new Error('article-archive-button ontbreekt'); clickElement(archiveButton); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="article-archive-modal"]'), WAIT_TIMEOUT, 'article-archive-modal niet gevonden'); const confirmButton=getFrameDocument(frame)?.querySelector('[data-testid="article-archive-confirm"]'); if(!confirmButton) throw new Error('article-archive-confirm ontbreekt'); clickElement(confirmButton); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="article-archive-status"]')?.textContent?.includes('Gearchiveerd'), WAIT_TIMEOUT, 'Artikelstatus werd niet gearchiveerd'); await navigateFrame(frame,'/voorraad'); await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="inventory-page"]'), WAIT_TIMEOUT, 'inventory-page niet gevonden na archiveren'); if(getFrameDocument(frame)?.querySelector(`[data-testid="inventory-row-${articleId}"]`)) throw new Error('Gearchiveerd artikel bleef zichtbaar in actieve voorraad') }, results)
    await runScenario('R12 Export-testdataset selectie activeert export op detailroute', async ()=>{ const exportFixture = await prepareReceiptExportFixture(frame); const targetBatchId = exportFixture.latestBatchId || exportFixture.batchId
    await navigateFrame(frame, `/winkels/batch/${encodeURIComponent(targetBatchId)}?fixture=export&t=${Date.now()}`); const detailDoc = await waitForCondition(()=>getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]') ? getFrameDocument(frame) : null, WAIT_TIMEOUT, 'receipt-detail-page niet gevonden voor export-testdataset'); const lineSelect = detailDoc.querySelector(`[data-testid="receipt-line-select-${exportFixture.exportLineId}"]`); const exportButton=getReceiptExportButton(detailDoc); if(!lineSelect||!exportButton) throw new Error('Export-testdataset selectie of export ontbreekt'); if(lineSelect.disabled) throw new Error('Export-testdatasetregel is niet selecteerbaar'); if(exportButton.disabled !== true) throw new Error('receipt-export-button hoort initieel uitgeschakeld te zijn'); nativeClick(lineSelect); const activeExportButton=await waitForCondition(()=>{ const liveDoc=getFrameDocument(frame); const button=getReceiptExportButton(liveDoc); return button && button.disabled===false ? button : null }, WAIT_TIMEOUT, 'receipt-export-button werd niet actief na selectie in export-testdataset'); const exactLine=getFrameDocument(frame)?.querySelector(`[data-testid="receipt-line-select-${exportFixture.exportLineId}"]`); if(!exactLine?.checked) throw new Error('Export-testdatasetregel bleef niet geselecteerd'); if(String(activeExportButton.textContent||'').trim().toLowerCase()!=='exporteren') throw new Error('receipt-export-button heeft onverwachte labeltekst') }, results)
    await runScenario('R13 Kassa importeert een .eml via de e-mail-dropzone', async ()=>{ const token = buildRegressionReceiptEmailToken(); const { importedReceipt } = await importEmailReceiptViaDropzone(frame, token); if (String(importedReceipt?.source_label || '').toLowerCase() !== 'e-mail') throw new Error('Nieuwe bon kreeg niet het bronlabel E-mail'); const statusMessage = await waitForCondition(() => { const doc = getFrameDocument(frame); return [...(doc?.querySelectorAll('.rz-inline-feedback--success') || [])].find((element) => element.textContent?.includes('E-mailbon ontvangen')) || null }, WAIT_TIMEOUT, 'Succesmelding voor e-mailimport niet zichtbaar'); if (!statusMessage.textContent?.includes('Kassa')) throw new Error('Succesmelding noemt Kassa niet') }, results)
    await runScenario('R14 Kassa toont een melding bij een dubbele .eml-import zonder extra bon', async ()=>{ const fixtureState = frame.__rezzervKassaReceiptFixture || {}; if (!fixtureState.token || !fixtureState.receiptTableId) throw new Error('Kassa-fixture voor duplicate test ontbreekt'); const feedback = await triggerDuplicateEmailReceiptViaDropzone(frame, fixtureState.token, fixtureState.receiptTableId); if (!feedback.textContent?.includes('niet opnieuw geladen')) throw new Error('Dubbele kassabonmelding heeft onverwachte tekst'); if (!getFrameDocument(frame)?.querySelector('[data-testid="kassa-email-dropzone"]')) throw new Error('E-mailbron bleef niet open bij duplicate import') }, results)
    await runScenario('R15 Verwijderen in Kassa maakt herimport van dezelfde .eml weer mogelijk', async ()=>{ const fixtureState = frame.__rezzervKassaReceiptFixture || {}; if (!fixtureState.token || !fixtureState.receiptTableId) throw new Error('Kassa-fixture voor verwijdertest ontbreekt'); await deleteReceiptViaKassa(frame, fixtureState.receiptTableId); const beforeReimport = await fetchKassaReceiptItems('1'); const beforeIds = new Set(beforeReimport.map((item) => String(item?.receipt_table_id || ''))); const { importedReceipt } = await importEmailReceiptViaDropzone(frame, fixtureState.token); if (beforeIds.has(String(importedReceipt?.receipt_table_id || ''))) throw new Error('Herimport na verwijderen leverde geen nieuwe bon op'); if (String(importedReceipt?.receipt_table_id || '') === String(fixtureState.receiptTableId)) throw new Error('Herimport na verwijderen hergebruikte onverwacht hetzelfde bon-id'); if (getFrameDocument(frame)?.querySelector('[data-testid="receipt-sourcehub-duplicate-feedback"]')) throw new Error('Herimport na verwijderen werd nog steeds als duplicate gemeld') }, results)
    await runScenario('R16 Kassa handmatige bestandsimport opent de nieuwe bon direct', async ()=>{ const importedReceipt = await importManualReceiptViaFileInput(frame); const detailDoc = getFrameDocument(frame); if (!detailDoc?.querySelector('[data-testid="receipt-detail-page"]')) throw new Error('Handmatig geïmporteerde bon opende niet in de detailkaart'); if (!String(importedReceipt?.receipt_table_id || '').trim()) throw new Error('Handmatige import gaf geen receipt_table_id terug') }, results)
    await runScenario('R17 Kassa camera-import opent de nieuwe bon direct', async ()=>{ const importedReceipt = await importCameraReceiptViaFileInput(frame); const detailDoc = getFrameDocument(frame); if (!detailDoc?.querySelector('[data-testid="receipt-detail-page"]')) throw new Error('Camera-import opende de nieuwe bon niet in de detailkaart'); if (!String(importedReceipt?.receipt_table_id || '').trim()) throw new Error('Camera-import gaf geen receipt_table_id terug') }, results)
    await runScenario('R18 Share-import voegt een nieuwe bon toe zonder crash', async ()=>{ const importedReceipt = await importShareReceiptViaApi(frame); if (!String(importedReceipt?.receipt_table_id || '').trim()) throw new Error('Share-import leverde geen receipt_table_id op'); if (!getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]')) throw new Error('Share-import opende de bon niet in Kassa') }, results)
    await runScenario('R19 Uitpakken toont alleen Kassa-bonnen met status Gecontroleerd en Controle nodig', async ()=>{ const seeded = await seedRegressionKassaReceipts(); const unpackItems = await fetchUnpackStartBatches('1'); if (unpackItems.some((item) => String(item?.receipt_table_id || '') === String(seeded?.receipts?.new?.receipt_table_id || ''))) throw new Error('Nieuw-status bon verscheen onterecht in Uitpakken'); await navigateFrame(frame,'/kassabonnen'); const reviewedRow = await waitForCondition(() => getReceiptBatchRow(getFrameDocument(frame), seeded?.receipts?.reviewed?.batch_id) || null, WAIT_TIMEOUT, 'Gecontroleerde bon ontbreekt in Uitpakken'); const reviewNeededRow = await waitForCondition(() => getReceiptBatchRow(getFrameDocument(frame), seeded?.receipts?.review_needed?.batch_id) || null, WAIT_TIMEOUT, 'Controle-nodig bon ontbreekt in Uitpakken'); if (!getBatchStatusCell(reviewedRow)?.textContent?.includes('Gecontroleerd')) throw new Error('Gecontroleerde bon toont geen status Gecontroleerd in Uitpakken'); if (!getBatchStatusCell(reviewNeededRow)?.textContent?.includes('Controle nodig')) throw new Error('Controle-nodig bon toont geen status Controle nodig in Uitpakken'); const rows = [...(getFrameDocument(frame)?.querySelectorAll('[data-testid^="receipt-batch-row-"]') || [])]; if (rows.some((row) => getBatchStatusCell(row)?.textContent?.includes('Nieuw'))) throw new Error('Uitpakken toont nog steeds een Nieuw-status rij') }, results)
    await runScenario('R20 Dubbelklik in Uitpakken opent het bestaande Kassabon-detailscherm', async ()=>{ const seeded = await seedRegressionKassaReceipts(); await navigateFrame(frame,'/kassabonnen'); const row = await waitForCondition(() => getReceiptBatchRow(getFrameDocument(frame), seeded?.receipts?.reviewed?.batch_id) || null, WAIT_TIMEOUT, 'Uitpakken-rij voor dubbelklik ontbreekt'); clickElement(row); doubleClickElement(row); const detailDoc = await waitForCondition(() => getFrameDocument(frame)?.querySelector('[data-testid="receipt-detail-page"]') ? getFrameDocument(frame) : null, WAIT_TIMEOUT, 'Bestaand Kassabon-detailscherm werd niet geopend'); if (!String(detailDoc?.body?.textContent || '').includes('Kassabon')) throw new Error('Detailscherm toont geen Kassabon-context na dubbelklik') }, results)
    await runScenario('R21 Gecontroleerde Kassa-bon kan via Uitpakken naar voorraad worden verwerkt', async ()=>{ const seeded = await seedRegressionKassaReceipts(); const result = await mapReceiptBatchLineAndProcess(frame, seeded?.receipts?.reviewed?.batch_id, seeded?.receipts?.reviewed?.article_name || 'Melk'); const latestHistory = result.historyRows.find((entry) => String(entry?.note || '').includes(`batch=${seeded?.receipts?.reviewed?.batch_id}`)); if (!latestHistory) throw new Error('Geen historie-entry gevonden voor de gecontroleerde bon'); if (!['store_import', 'receipt'].includes(String(latestHistory?.source || ''))) throw new Error('Gecontroleerde bon schreef geen receipt/store_import event naar historie'); if (!String(latestHistory?.note || '').includes('provider=receipt')) throw new Error('Historie-entry van gecontroleerde bon mist provider=receipt in de note') }, results)
    await runScenario('R22 Controle-nodig bon kan via Uitpakken naar voorraad worden verwerkt', async ()=>{ const seeded = await seedRegressionKassaReceipts(); const result = await mapReceiptBatchLineAndProcess(frame, seeded?.receipts?.review_needed?.batch_id, seeded?.receipts?.review_needed?.article_name || 'Tomaten'); const latestHistory = result.historyRows.find((entry) => String(entry?.note || '').includes(`batch=${seeded?.receipts?.review_needed?.batch_id}`)); if (!latestHistory) throw new Error('Geen historie-entry gevonden voor de controle-nodig bon'); if (!['store_import', 'receipt'].includes(String(latestHistory?.source || ''))) throw new Error('Controle-nodig bon schreef geen receipt/store_import event naar historie'); if (!String(latestHistory?.note || '').includes('provider=receipt')) throw new Error('Historie-entry van controle-nodig bon mist provider=receipt in de note') }, results)
    await runScenario('R23 Uitpakken-adapter maakt geen duplicaatbatch per receipt', async ()=>{ const seeded = await seedRegressionKassaReceipts(); const first = await fetchUnpackStartBatches('1'); const second = await fetchUnpackStartBatches('1'); const reviewedId = String(seeded?.receipts?.reviewed?.batch_id || ''); const reviewNeededId = String(seeded?.receipts?.review_needed?.batch_id || ''); const firstReviewedCount = first.filter((item) => String(item?.batch_id || '') === reviewedId).length; const secondReviewedCount = second.filter((item) => String(item?.batch_id || '') === reviewedId).length; const firstReviewNeededCount = first.filter((item) => String(item?.batch_id || '') === reviewNeededId).length; const secondReviewNeededCount = second.filter((item) => String(item?.batch_id || '') === reviewNeededId).length; if (firstReviewedCount !== 1 || secondReviewedCount !== 1 || firstReviewNeededCount !== 1 || secondReviewNeededCount !== 1) throw new Error('Uitpakken-adapter maakte dubbele batchrecords voor dezelfde kassabon') }, results)
    await runScenario('R24 Historie bewaart purchase-events uit Uitpakken met receipt-provider noot', async ()=>{ const seeded = await seedRegressionKassaReceipts(); await mapReceiptBatchLineAndProcess(frame, seeded?.receipts?.reviewed?.batch_id, seeded?.receipts?.reviewed?.article_name || 'Melk'); const historyRows = await getArticleHistoryRows(seeded?.receipts?.reviewed?.article_name || 'Melk'); const receiptHistory = historyRows.filter((entry) => String(entry?.note || '').includes('provider=receipt')); if (!receiptHistory.length) throw new Error('Historie toont geen purchase-event met receipt-provider'); if (!receiptHistory.some((entry) => String(entry?.note || '').includes(`batch=${seeded?.receipts?.reviewed?.batch_id}`))) throw new Error('Historie-entry verwijst niet naar de verwerkte receipt-batch') }, results)
  } finally { removeExistingFrame() }
  return results
}
