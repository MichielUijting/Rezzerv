export const JUMBO_BOOKMARKLET_VERSION = 5
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/bestellingen'
export const JUMBO_POC_FRAGMENT_PREFIX = '#jumbo-poc-v5='

function validInhuisCallbackUrl(value) {
  try {
    const url = new URL(value)
    return (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      !!url.hostname &&
      !url.username &&
      !url.password
    )
  } catch {
    return false
  }
}

export function parseJumboReceiptLayout(rawJson) {
  let data
  try {
    data = JSON.parse(rawJson)
  } catch {
    return { items: [], parseError: 'Invalid receipt JSON' }
  }

  const textObjects = []
  try {
    const sections = data.documents[0].documents[0].printSections
    for (const section of sections) {
      for (const object of Array.isArray(section?.textObjects) ? section.textObjects : []) {
        for (const line of Array.isArray(object?.textLines) ? object.textLines : []) {
          const texts = (Array.isArray(line?.texts) ? line.texts : []).map((entry) => String(entry?.text || ''))
          textObjects.push(texts)
        }
      }
    }
  } catch {
    return { items: [], parseError: 'Unexpected receipt structure' }
  }

  const items = []
  let total = null
  let paymentMethod = null
  const vatLines = []
  let itemCount = null

  let index = 0
  let inItems = false
  while (index < textObjects.length) {
    const texts = textObjects[index]
    const joined = texts.map((text) => text.trim()).filter(Boolean).join(' ')

    if (joined.includes('OMSCHRIJVING') && joined.includes('BEDRAG')) {
      inItems = true
      index += 1
      if (index < textObjects.length) {
        const separator = textObjects[index].join('')
        if (separator.startsWith('=') || separator.startsWith('-')) index += 1
      }
      continue
    }

    if (inItems && joined.startsWith('Totaal')) {
      inItems = false
      for (const text of texts) {
        const value = Number.parseFloat(text.trim().replace(',', '.'))
        if (Number.isFinite(value)) total = value
      }
      index += 1
      continue
    }

    if (inItems) {
      const first = texts[0]?.trim() || ''
      if (!first || first.startsWith('=') || first.startsWith('-')) {
        index += 1
        continue
      }

      const quantityMatch = first.match(/^\s*(\d+)\s*[Xx]\s*(\d+[,.]\d+)/)
      if (quantityMatch && items.length) {
        const quantity = Number.parseInt(quantityMatch[1], 10)
        const unitPrice = Number.parseFloat(quantityMatch[2].replace(',', '.'))
        items[items.length - 1].quantity = quantity
        items[items.length - 1].unitPrice = unitPrice
        for (const text of [...texts].reverse()) {
          const value = Number.parseFloat(text.trim().replace(',', '.'))
          if (Number.isFinite(value)) {
            items[items.length - 1].price = value
            break
          }
        }
        index += 1
        continue
      }

      let price = null
      for (const text of [...texts].reverse()) {
        const value = Number.parseFloat(text.trim().replace(',', '.'))
        if (Number.isFinite(value)) {
          price = value
          break
        }
      }

      const isPromo = texts.length > 1 && texts[1].trim() === 'P'
      items.push({
        name: first,
        price,
        quantity: 1,
        unitPrice: price,
        isPromo,
        isDeposit: first.toUpperCase() === 'STATIEGELD',
      })
      index += 1
      continue
    }

    if (joined.startsWith('Betaald')) {
      index += 1
      if (index < textObjects.length) {
        paymentMethod = textObjects[index][0]?.trim() || null
      }
      index += 1
      continue
    }

    if (joined.startsWith('BTW%') || joined.includes('Bedrag excl')) {
      index += 1
      while (index < textObjects.length) {
        const values = textObjects[index]
        const valueJoined = values.map((value) => value.trim()).filter(Boolean).join(' ')
        if (!valueJoined || valueJoined.startsWith('-') || valueJoined.startsWith('=')) break
        if (valueJoined.includes('%') || valueJoined.startsWith('BTW Totaal')) {
          vatLines.push(values.map((value) => value.trim()).filter(Boolean))
        }
        index += 1
      }
      continue
    }

    const countMatch = joined.match(/Aantal artikelen.*?:\s*(\d+)/)
    if (countMatch) {
      itemCount = Number.parseInt(countMatch[1], 10)
      index += 1
      continue
    }

    index += 1
  }

  const products = items.filter((item) => !item.isDeposit)
  const deposits = items.filter((item) => item.isDeposit)
  const vatSummary = vatLines
    .filter((parts) => parts.length >= 3 && !parts[0].includes('Totaal'))
    .map((parts) => ({
      rate: parts[0],
      amountExcl: parts[1] || null,
      vatAmount: parts[2] || null,
    }))

  return {
    items: products,
    deposits,
    total,
    paymentMethod,
    vatSummary,
    itemCount,
  }
}

export function buildJumboPocBookmarklet(inhuisCallbackUrl) {
  const callbackUrl = String(inhuisCallbackUrl || '').replace(/#.*$/, '')
  if (!validInhuisCallbackUrl(callbackUrl)) {
    throw new Error('Ongeldige Inhuis-callback voor Jumbo-POC')
  }

  const parserSource = parseJumboReceiptLayout.toString()

  return (
    'javascript:(async()=>{' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const C=' + JSON.stringify(callbackUrl) + ';' +
    'const P=' + JSON.stringify(JUMBO_POC_FRAGMENT_PREFIX) + ';' +
    'const parseReceipt=' + parserSource + ';' +
    'const ID="__inhuis_jumbo_redirect_poc";' +
    'let box=document.getElementById(ID);' +
    'if(!box){box=document.createElement("div");box.id=ID;box.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:520px;padding:12px 14px;background:#fff;border:2px solid currentColor;color:#111;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);white-space:pre-wrap";document.documentElement.appendChild(box);}' +
    'const show=m=>{box.textContent="Inhuis Jumbo receipt-POC\\n"+m;try{console.info("[Inhuis Jumbo receipt-POC]",m);}catch{}};' +
    'const ret=o=>{show("Resultaat gereed; terug naar Inhuis…");location.href=C+P+encodeURIComponent(JSON.stringify(o));};' +
    'const gql=async(operationName,query,variables)=>{' +
    'const r=await fetch("/api/graphql",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json",Accept:"application/json","apollographql-client-name":"JUMBO_WEB-orders","apollographql-client-version":"master-v29.2.0-web","x-source":"JUMBO_WEB-orders"},body:JSON.stringify({operationName,query,variables})});' +
    'const j=await r.json().catch(()=>null);' +
    'if(!r.ok)throw new Error("Jumbo GraphQL HTTP "+r.status);' +
    'if(!j||typeof j!=="object")throw new Error("Jumbo GraphQL gaf geen geldig JSON-antwoord");' +
    'if(Array.isArray(j.errors)&&j.errors.length)throw new Error(String(j.errors[0]?.message||"Jumbo GraphQL-fout"));' +
    'if(!j.data||typeof j.data!=="object")throw new Error("Jumbo GraphQL bevat geen data");' +
    'return j.data;};' +
    'try{' +
    'show("Stap 1/4: Jumbo bonnenlijst opvragen…");' +
    'const listQuery="query GetOnlineOrdersAndStoreReceipts($ordersInput: OrdersInput!, $page: Int, $pageSize: Int) { storeReceipts: receiptOverview(page: $page, pageSize: $pageSize) { totalResults pageSize currentPage receipts { transactionId purchaseEndOn receiptSource store { storeId name } } } onlineOrders: orders(input: $ordersInput) { totalCount } }";' +
    'const list=await gql("GetOnlineOrdersAndStoreReceipts",listQuery,{ordersInput:{offset:0,limit:1,direction:"DESC",sortBy:"deliveryDate",statusCategory:"CLOSED"},page:0,pageSize:10});' +
    'const s=list.storeReceipts||{};' +
    'const receipts=Array.isArray(s.receipts)?s.receipts:[];' +
    'const totalResults=Number(s.totalResults||receipts.length||0);' +
    'show("Stap 2/4: "+String(totalResults)+" bon(nen) gevonden.");' +
    'if(!receipts.length){ret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,current_page:Number(s.currentPage||0),first_detail:null});return;}' +
    'const first=receipts[0];' +
    'const transactionId=String(first?.transactionId||"").trim();' +
    'if(!transactionId)throw new Error("De eerste Jumbo-kassabon heeft geen transactionId");' +
    'show("Stap 3/4: detail van nieuwste bon ophalen…");' +
    'const detailQuery="query GetDigitalReceipt($transactionId: String) { receipt(transactionId: $transactionId) { receiptImage { image type receiptPoints { earned newBalance oldBalance redeemed } } store { name location { address { city houseNumber postalCode street } } } purchaseEndOn receiptSource transactionId } }";' +
    'const detailData=await gql("GetDigitalReceipt",detailQuery,{transactionId});' +
    'const receipt=detailData.receipt;' +
    'if(!receipt||!receipt.transactionId)throw new Error("Jumbo gaf geen detail voor kassabon "+transactionId);' +
    'const image=receipt.receiptImage||{};' +
    'const parsed=parseReceipt(image.image);' +
    'show("Stap 4/4: bonlayout ontleed; "+String(Array.isArray(parsed.items)?parsed.items.length:0)+" productregel(s).");' +
    'ret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,current_page:Number(s.currentPage||0),first_detail:{transactionId:String(receipt.transactionId||""),purchaseEndOn:receipt.purchaseEndOn||null,receiptSource:receipt.receiptSource||null,storeName:receipt.store?.name||null,receiptImageType:image.type||null,parsed}});' +
    '}catch(err){' +
    'const message=String(err&&err.message?err.message:err);' +
    'show("POC-fout: "+message);' +
    'ret({version:V,ok:false,source_origin:location.origin,error:message});' +
    '}' +
    '})()'
  )
}
