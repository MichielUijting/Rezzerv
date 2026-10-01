export const JUMBO_WEB_ORIGIN = 'https://www.jumbo.com'
export const JUMBO_BOOKMARKLET_VERSION = 3
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/bestellingen'

function jumboReceiptPocRunner(INHUIS_ORIGIN) {
  const target = window.opener
  if (!target) {
    alert('Jumbo POC diagnose: window.opener ontbreekt. Open Jumbo opnieuw vanuit Inhuis > Winkelkoppelingen en start daarna de favoriet opnieuw.')
    return
  }

  target.postMessage({
    type: 'inhuis:jumbo-poc-diagnostic',
    stage: 'RUNNER_START',
    detail: location.origin,
  }, INHUIS_ORIGIN)

  function post(data) {
    target.postMessage(data, INHUIS_ORIGIN)
  }

  async function graphql(operationName, query, variables) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 20000)
    let response
    try {
      response = await fetch('/api/graphql', {
        method: 'POST',
        credentials: 'include',
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'apollographql-client-name': 'JUMBO_WEB-orders',
          'apollographql-client-version': 'master-v29.2.0-web',
          'x-source': 'JUMBO_WEB-orders',
        },
        body: JSON.stringify({ operationName, query, variables }),
      })
    } catch (error) {
      if (error?.name === 'AbortError') {
        throw new Error('Jumbo reageerde niet binnen 20 seconden. Probeer de POC opnieuw.')
      }
      throw error
    } finally {
      clearTimeout(timeout)
    }

    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      throw new Error('Jumbo GraphQL gaf HTTP ' + response.status)
    }
    if (!payload || typeof payload !== 'object') {
      throw new Error('Jumbo GraphQL gaf geen geldig antwoord')
    }
    if (Array.isArray(payload.errors) && payload.errors.length) {
      const first = payload.errors[0] || {}
      throw new Error(String(first.message || first.extensions?.code || 'Jumbo GraphQL-fout'))
    }
    if (!payload.data || typeof payload.data !== 'object') {
      throw new Error('Jumbo GraphQL bevat geen data')
    }
    return payload.data
  }

  function inspectReceiptLayout(raw) {
    const proof = {
      type: typeof raw,
      length: typeof raw === 'string' ? raw.length : 0,
      textLineCount: 0,
      hasItemsHeader: false,
      hasTotalLine: false,
    }
    if (typeof raw !== 'string' || !raw.trim()) return proof

    try {
      const parsed = JSON.parse(raw)
      const sections = parsed?.documents?.[0]?.documents?.[0]?.printSections
      if (!Array.isArray(sections)) return proof
      for (const section of sections) {
        for (const object of Array.isArray(section?.textObjects) ? section.textObjects : []) {
          for (const line of Array.isArray(object?.textLines) ? object.textLines : []) {
            const texts = (Array.isArray(line?.texts) ? line.texts : [])
              .map((item) => String(item?.text || '').trim())
              .filter(Boolean)
            if (!texts.length) continue
            proof.textLineCount += 1
            const joined = texts.join(' ')
            if (joined.includes('OMSCHRIJVING') && joined.includes('BEDRAG')) proof.hasItemsHeader = true
            if (/^Totaal\b/i.test(joined)) proof.hasTotalLine = true
          }
        }
      }
    } catch {
      return proof
    }
    return proof
  }

  const listQuery = `
    query GetOnlineOrdersAndStoreReceipts($ordersInput: OrdersInput!, $page: Int, $pageSize: Int) {
      storeReceipts: receiptOverview(page: $page, pageSize: $pageSize) {
        totalResults
        pageSize
        currentPage
        receipts {
          transactionId
          purchaseEndOn
          receiptSource
          store { storeId name }
          pointBalance
        }
      }
      onlineOrders: orders(input: $ordersInput) {
        orders { orderId }
        totalCount
      }
    }
  `

  const detailQuery = `
    query GetDigitalReceipt($transactionId: String) {
      receipt(transactionId: $transactionId) {
        receiptImage {
          image
          type
          receiptPoints { earned newBalance oldBalance redeemed }
        }
        store { name location { address { city houseNumber postalCode street } } }
        purchaseEndOn
        receiptSource
        transactionId
      }
    }
  `

  ;(async () => {
    try {
      post({ type: 'inhuis:jumbo-poc-diagnostic', stage: 'GRAPHQL_LIST_START', detail: location.href })
      post({ type: 'inhuis:jumbo-poc-progress', message: 'Jumbo-kassabonnen zoeken…' })
      const listData = await graphql(
        'GetOnlineOrdersAndStoreReceipts',
        listQuery,
        {
          ordersInput: {
            offset: 0,
            limit: 1,
            direction: 'DESC',
            sortBy: 'deliveryDate',
            statusCategory: 'CLOSED',
          },
          page: 0,
          pageSize: 10,
        },
      )

      post({ type: 'inhuis:jumbo-poc-diagnostic', stage: 'GRAPHQL_LIST_OK', detail: 'Antwoord ontvangen' })
      const storeReceipts = listData?.storeReceipts || {}
      const receipts = Array.isArray(storeReceipts.receipts) ? storeReceipts.receipts : []
      if (!receipts.length) {
        post({
          type: 'inhuis:jumbo-poc-result',
          result: {
            totalResults: Number(storeReceipts.totalResults || 0),
            currentPage: Number(storeReceipts.currentPage || 0),
            receipts: [],
            firstDetail: null,
          },
        })
        target.focus()
        return
      }

      const first = receipts[0]
      const transactionId = String(first?.transactionId || '').trim()
      if (!transactionId) throw new Error('De eerste Jumbo-kassabon heeft geen transactionId')

      post({ type: 'inhuis:jumbo-poc-progress', message: 'Eerste Jumbo-kassabon ophalen…' })
      const detailData = await graphql('GetDigitalReceipt', detailQuery, { transactionId })
      const receipt = detailData?.receipt
      if (!receipt || !receipt.transactionId) {
        throw new Error('Jumbo gaf geen detail voor kassabon ' + transactionId)
      }

      const image = receipt.receiptImage || {}
      post({
        type: 'inhuis:jumbo-poc-result',
        result: {
          totalResults: Number(storeReceipts.totalResults || receipts.length),
          currentPage: Number(storeReceipts.currentPage || 0),
          receipts: receipts.map((row) => ({
            transactionId: String(row?.transactionId || ''),
            purchaseEndOn: row?.purchaseEndOn || null,
            receiptSource: row?.receiptSource || null,
            storeName: row?.store?.name || null,
          })),
          firstDetail: {
            transactionId: String(receipt.transactionId || ''),
            purchaseEndOn: receipt.purchaseEndOn || null,
            receiptSource: receipt.receiptSource || null,
            storeName: receipt.store?.name || null,
            receiptImageType: image.type || null,
            layoutProof: inspectReceiptLayout(image.image),
          },
        },
      })
      target.focus()
    } catch (error) {
      post({
        type: 'inhuis:jumbo-poc-error',
        message: String(error && error.message ? error.message : error),
      })
      target.focus()
    }
  })()
}

function validInhuisOrigin(value) {
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[[^\]]+\]|[^/]+)(:\d+)?$/i.test(value)
}

export function buildJumboPocBookmarklet() {
  return (
    'javascript:(()=>{' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const ID="__inhuis_jumbo_poc_diag";' +
    'const ts=()=>new Date().toLocaleTimeString();' +
    'let box=document.getElementById(ID);' +
    'if(!box){box=document.createElement("div");box.id=ID;box.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:520px;padding:12px 14px;background:#fff;border:2px solid #005F6A;color:#111;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);white-space:pre-wrap";document.documentElement.appendChild(box);}' +
    'const lines=[];' +
    'const show=(m)=>{lines.push(ts()+"  "+m);box.textContent="Inhuis Jumbo POC diagnose\\n"+lines.join("\\n");};' +
    'const log=(level,m,o)=>{try{(console[level]||console.log).call(console,"[Inhuis Jumbo POC] "+m,o||"");}catch{}};' +
    'show("BOOKMARKLET_START v"+V);' +
    'show("URL: "+location.href);' +
    'show("ORIGIN: "+location.origin);' +
    'log("info","bookmarklet gestart",{version:V,url:location.href,origin:location.origin});' +
    'const W=window.opener;' +
    'show("WINDOW_OPENER: "+(W?"AANWEZIG":"ONTBREEKT"));' +
    'if(!W){log("error","window.opener ontbreekt");show("STOP: geen opener; handshake kan niet worden verstuurd.");return;}' +
    'let done=false;' +
    'window.addEventListener("message",e=>{' +
    'log("info","message ontvangen",{origin:e.origin,sourceMatches:e.source===W,type:e.data&&e.data.type});' +
    'if(done||e.source!==W||!e.data||e.data.type!=="inhuis:jumbo-poc-script")return;' +
    'if(!/^https?:\\/\\/(localhost|127\\.0\\.0\\.1|\\[[^\\]]+\\]|[^/]+)(:\\d+)?$/i.test(e.origin)){show("ANTWOORD_GEWEIGERD: onverwachte Inhuis-origin "+String(e.origin||"onbekend"));log("error","onverwachte Inhuis-origin",e.origin);return;}' +
    'done=true;' +
    'show("INHUIS_ANTWOORD: ontvangen van "+e.origin);' +
    'try{new Function(e.data.script)();show("POC_SCRIPT: gestart");}catch(err){show("POC_SCRIPT_FOUT: "+String(err&&err.message||err));log("error","POC-script fout",err);}' +
    '},{once:false});' +
    'try{' +
    'W.postMessage({type:"inhuis:jumbo-poc-diagnostic",stage:"BOOKMARKLET_START",detail:location.origin+" "+location.pathname,bookmarklet_version:V},"*");' +
    'W.postMessage({type:"inhuis:jumbo-poc-diagnostic",stage:"HANDSHAKE_SENT",detail:location.origin,bookmarklet_version:V},"*");' +
    'W.postMessage({type:"inhuis:jumbo-poc-handshake",bookmarklet_version:V},"*");' +
    'show("HANDSHAKE_SENT: ja");' +
    'log("info","handshake verzonden",{target:"*",version:V});' +
    '}catch(err){show("HANDSHAKE_FOUT: "+String(err&&err.message||err));log("error","handshake verzenden mislukt",err);return;}' +
    'setTimeout(()=>{if(!done){show("INHUIS_ANTWOORD: NIET ontvangen binnen 4 seconden");log("error","geen antwoord van Inhuis binnen 4 seconden");}},4000);' +
    '})()'
  )
}

export function buildJumboPocPageScript(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  if (!validInhuisOrigin(origin)) throw new Error('Ongeldige Inhuis-origin voor Jumbo-POC')
  return '(' + jumboReceiptPocRunner.toString() + ')(' + JSON.stringify(origin) + ')'
}
