import { getLayer1Fixture } from './layer1RegressionFixture'

const FRAME_ID = 'rezzerv-layer2-runner-frame'
const WAIT_TIMEOUT = 9000
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
async function requestJson(path, init = {}) {
  const response = await fetch(path, {
    method: init.method || 'GET',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    body: init.body,
  })
  if (!response.ok) throw new Error(`Request naar ${path} mislukte met status ${response.status}`)
  return response.json()
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
  } finally { removeExistingFrame() }
  return results
}
