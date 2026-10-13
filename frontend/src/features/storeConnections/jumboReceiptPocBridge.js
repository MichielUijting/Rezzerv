import { jumboDay, jumboDateWindow, selectJumboHistory, JUMBO_BATCH_LIMIT, JUMBO_MAX_PAGES } from './jumboReceiptBatch.js'

export const JUMBO_BOOKMARKLET_VERSION = 6
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/bestellingen'
export const JUMBO_POC_FRAGMENT_PREFIX = '#jumbo-poc-v6='

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

export function buildJumboPocBookmarklet(inhuisCallbackUrl, dateRange) {
  const callbackUrl = String(inhuisCallbackUrl || '').replace(/#.*$/, '')
  if (!validInhuisCallbackUrl(callbackUrl)) {
    throw new Error('Ongeldige Inhuis-callback voor Jumbo-POC')
  }

  const parserSource = parseJumboReceiptLayout.toString()
  const range = dateRange || (() => {
    const now = new Date()
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const start = new Date(end)
    start.setDate(start.getDate() - 29)
    const toDay = (d) => [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
    return { from_date: toDay(start), to_date: toDay(end) }
  })()
  const checkedRange = jumboDateWindow(range.from_date, range.to_date)

  return (
    'javascript:(async()=>{' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const C=' + JSON.stringify(callbackUrl) + ';' +
    'const P=' + JSON.stringify(JUMBO_POC_FRAGMENT_PREFIX) + ';' +
    'const parseReceipt=' + parserSource + ';' +
    'const jumboDay=' + jumboDay.toString() + ';' +
    'const jumboDateWindow=' + jumboDateWindow.toString() + ';' +
    'const selectJumboHistory=' + selectJumboHistory.toString() + ';' +
    'const RANGE=' + JSON.stringify(checkedRange) + ';' +
    'const LIMIT=' + String(JUMBO_BATCH_LIMIT) + ';' +
    'const MAX_PAGES=' + String(JUMBO_MAX_PAGES) + ';' +
    'const ID="__inhuis_jumbo_redirect_poc";' +
    'let box=document.getElementById(ID);' +
    'if(!box){box=document.createElement("div");box.id=ID;box.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:520px;padding:12px 14px;background:#fff;border:2px solid currentColor;color:#111;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);white-space:pre-wrap";document.documentElement.appendChild(box);}' +
    'const show=m=>{box.textContent="Inhuis Jumbo receipt-POC\\n"+m;try{console.info("[Inhuis Jumbo receipt-POC]",m);}catch{}};' +
    'const ret=o=>{show("Resultaat gereed; terug naar Inhuis…");if(encodeURIComponent(JSON.stringify(o)).length>48000)o={version:V,ok:false,source_origin:location.origin,error:"Te veel bongegevens voor veilige overdracht. Kies een kortere Jumbo-periode."};location.href=C+P+encodeURIComponent(JSON.stringify(o));};' +
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
    "const history=[];let totalResults=null;let finished=false;\nfor(let page=0;page<MAX_PAGES;page++){\nshow(\"Jumbo geschiedenis ophalen: pagina \"+String(page+1));\nconst list=await gql(\"GetOnlineOrdersAndStoreReceipts\",listQuery,{ordersInput:{offset:0,limit:1,direction:\"DESC\",sortBy:\"deliveryDate\",statusCategory:\"CLOSED\"},page,pageSize:10});\nconst s=list.storeReceipts||{};const receipts=s.receipts;\nif(!Array.isArray(receipts))throw new Error(\"Jumbo gaf geen geldige geschiedenis terug.\");\nconst count=Number(s.totalResults);\nif(!Number.isSafeInteger(count)||count<0||count>300)throw new Error(\"Jumbo-bonnenaantal buiten veilige limiet.\");\nif(totalResults===null)totalResults=count;\nif(count!==totalResults)throw new Error(\"Jumbo-bonnenlijst is tijdens ophalen veranderd.\");\nif(Number(s.currentPage)!==page)throw new Error(\"Jumbo-paginering wijkt af.\");\nhistory.push(...receipts);\nif(history.length>=totalResults){finished=true;break;}\nif(!receipts.length)throw new Error(\"Jumbo retourneerde een lege tussenpagina.\");\n}\nif(!finished)throw new Error(\"Jumbo-geschiedenis heeft meer paginas dan veilig toegestaan.\");\nconst selected=selectJumboHistory(history,RANGE.from_date,RANGE.to_date,LIMIT);\nif(!selected.length){ret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,date_range:RANGE,details:[],first_detail:null});return;}\nconst detailQuery=\"query GetDigitalReceipt($transactionId: String) { receipt(transactionId: $transactionId) { receiptImage { image type receiptPoints { earned newBalance oldBalance redeemed } } store { name location { address { city houseNumber postalCode street } } } purchaseEndOn receiptSource transactionId } }\";\nconst details=[];\nfor(const row of selected){\nconst transactionId=String(row.transactionId||\"\").trim();\nshow(\"Jumbo-bondetail \"+String(details.length+1)+\"/\"+String(selected.length));\nconst detailData=await gql(\"GetDigitalReceipt\",detailQuery,{transactionId});\nconst receipt=detailData.receipt;\nif(!receipt||String(receipt.transactionId||\"\")!==transactionId)throw new Error(\"Jumbo-detail komt niet overeen met historiebon.\");\nif(jumboDay(receipt.purchaseEndOn)!==jumboDay(row.purchaseEndOn))throw new Error(\"Jumbo-bondatum verschilt van historiedatum.\");\nconst image=receipt.receiptImage||{};const parsed=parseReceipt(image.image);\nif(parsed.parseError)throw new Error(\"Jumbo-bonlayout kon niet worden ontleed.\");\ndetails.push({transactionId,purchaseEndOn:receipt.purchaseEndOn,receiptSource:receipt.receiptSource||null,storeName:receipt.store?.name||null,receiptImageType:image.type||null,parsed});\n}\nret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,date_range:RANGE,details,first_detail:details[0]||null});" +
    '}catch(err){' +
    'const message=String(err&&err.message?err.message:err);' +
    'show("POC-fout: "+message);' +
    'ret({version:V,ok:false,source_origin:location.origin,error:message});' +
    '}' +
    '})()'
  )
}
