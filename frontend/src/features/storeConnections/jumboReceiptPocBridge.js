export const JUMBO_WEB_ORIGIN = 'https://www.jumbo.com'
export const JUMBO_BOOKMARKLET_VERSION = 1
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/account/inloggen'

function jumboReceiptPocRunner(INHUIS_ORIGIN) {
  const target = window.opener
  if (!target) {
    alert('De bestaande Inhuis-sessie is niet meer beschikbaar. Open Jumbo opnieuw via Inhuis > Winkelkoppelingen.')
    return
  }

  function post(data) {
    target.postMessage(data, INHUIS_ORIGIN)
  }

  async function graphql(operationName, query, variables) {
    const response = await fetch('/api/graphql', {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'apollographql-client-name': 'JUMBO_WEB-orders',
        'apollographql-client-version': 'master-v29.2.0-web',
        'x-source': 'JUMBO_WEB-orders',
      },
      body: JSON.stringify({ operationName, query, variables }),
    })

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

export function buildJumboPocBookmarklet(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  if (!validInhuisOrigin(origin)) throw new Error('Ongeldige Inhuis-origin voor Jumbo-POC')

  return (
    'javascript:(()=>{' +
    'const O=' + JSON.stringify(origin) + ';' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const W=window.opener;' +
    'if(!W){alert("Open Jumbo eerst vanuit Inhuis > Winkelkoppelingen. Laat dat Inhuis-tabblad open en gebruik daarna deze favoriet.");return;}' +
    'let done=false;' +
    'window.addEventListener("message",e=>{' +
    'if(done||e.origin!==O||e.source!==W||!e.data||e.data.type!=="inhuis:jumbo-poc-script")return;' +
    'done=true;' +
    'try{new Function(e.data.script)();}catch(err){alert("Jumbo-POC kon niet starten: "+String(err&&err.message||err));}' +
    '},{once:false});' +
    'W.postMessage({type:"inhuis:jumbo-poc-handshake",bookmarklet_version:V},O);' +
    'setTimeout(()=>{if(!done)alert("De bestaande Inhuis-sessie reageert niet. Open Jumbo opnieuw via Inhuis > Winkelkoppelingen.");},4000);' +
    '})()'
  )
}

export function buildJumboPocPageScript(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  if (!validInhuisOrigin(origin)) throw new Error('Ongeldige Inhuis-origin voor Jumbo-POC')
  return '(' + jumboReceiptPocRunner.toString() + ')(' + JSON.stringify(origin) + ')'
}
