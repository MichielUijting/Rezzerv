import { jumboDay, jumboDateWindow, selectJumboHistory, JUMBO_BATCH_LIMIT, JUMBO_MAX_PAGES } from './jumboReceiptBatch.js'

export const JUMBO_BOOKMARKLET_VERSION = 14
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/bestellingen'
export const JUMBO_POC_FRAGMENT_PREFIX = '#jumbo-poc-v14='

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

// Literal bookmarklet source: the production minifier must never rewrite or
// rename identifiers inside the JavaScript that runs on www.jumbo.com.
// Keep in sync with parseJumboReceiptLayout; browser contract exercises both.
const JUMBO_BOOKMARKLET_PARSER_SOURCE = `
function parseReceipt(rawJson) {
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

      const quantityMatch = first.match(/^\\s*(\\d+)\\s*[Xx]\\s*(\\d+[,.]\\d+)/)
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

    const countMatch = joined.match(/Aantal artikelen.*?:\\s*(\\d+)/)
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
`

// Keep bookmarklet helper source stable after Vite/esbuild minification.
// Function#toString on imported helpers captures renamed symbols from the bundle
// (for example "tf"), which do not exist in Jumbo's browsing context.
const JUMBO_BOOKMARKLET_HELPER_SOURCE = `
const jumboDay = function(value) {
  if (typeof value !== 'string') return ''
  const m = value.match(/^(20\\d{2})-(\\d{2})-(\\d{2})(?:[T ](\\d{2}):(\\d{2})(?::(\\d{2})(?:\\.(\\d{1,9}))?)?(Z|[+-]\\d{2}:?\\d{2})?)?$/)
  if (!m) return ''
  const day = m[1] + '-' + m[2] + '-' + m[3]
  const dt = new Date(day + 'T00:00:00Z')
  if (Number.isNaN(dt.valueOf()) || dt.toISOString().slice(0, 10) !== day) return ''
  if (m[4] !== undefined) {
    const hh = Number(m[4])
    const mm = Number(m[5])
    const ss = m[6] === undefined ? 0 : Number(m[6])
    if (hh > 23 || mm > 59 || ss > 59) return ''
    const offset = m[8]
    if (offset && offset !== 'Z') {
      const digits = offset.slice(1).replace(':', '')
      if (Number(digits.slice(0, 2)) > 23 || Number(digits.slice(2)) > 59) return ''
    }
  }
  return day
};
const jumboDateWindow = function(from, to) {
  const start = jumboDay(from)
  const end = jumboDay(to)
  if (!start || !end || start !== from || end !== to || start > end) {
    throw new Error('Stel een geldige Jumbo-begindatum en einddatum in.')
  }
  return { from_date: start, to_date: end }
};
const selectJumboHistory = function(receipts, from, to, max = JUMBO_BATCH_LIMIT) {
  jumboDateWindow(from, to)
  if (!Array.isArray(receipts) || receipts.length > 5000 ||
      !Number.isInteger(max) || max < 1 || max > JUMBO_BATCH_LIMIT) {
    throw new Error('Ongeldige Jumbo-geschiedenislijst.')
  }
  const selected = []
  const seen = new Set()
  for (const [index, receipt] of receipts.entries()) {
    const id = typeof receipt?.transactionId === 'string' ? receipt.transactionId : ''
    const day = jumboDay(receipt?.purchaseEndOn)
    const prefix = 'Jumbo-historie, regel ' + String(index + 1) + ': '
    if (!id) {
      throw new Error(prefix + 'bonnummer ontbreekt of is geen tekst. Geen import uitgevoerd.')
    }
    if (!/^[\x21-\x7E]{4,100}$/.test(id)) {
      const reason = id.length < 4 ? 'te kort' :
        id.length > 100 ? 'te lang' :
        /\\s/.test(id) ? 'bevat spaties of witruimte' :
        /[^\\x00-\\x7F]/.test(id) ? 'bevat niet-ASCII-tekens' :
        'bevat een ongeldig of niet-afdrukbaar teken'
      throw new Error(prefix + 'bonnummer heeft een onverwacht formaat (' + reason + '). Geen import uitgevoerd.')
    }
    if (!day) {
      const value = receipt?.purchaseEndOn
      const reason = value == null || value === '' ? 'ontbreekt' :
        typeof value !== 'string' ? 'is geen tekstwaarde' :
        /^[0-9]{4}-[0-9]{2}-[0-9]{2}/.test(value) ? 'begint als ISO-datum maar heeft een ongeldige datum of tijdsaanduiding' :
        /^[0-9]{2}[-/][0-9]{2}[-/][0-9]{4}/.test(value) ? 'gebruikt dag-maand-jaar-notatie' :
        /^[0-9]{4}[/][0-9]{2}[/][0-9]{2}/.test(value) ? 'gebruikt schuine strepen in jaar-maand-dag' :
        'heeft een andere datumnotatie'
      throw new Error(prefix + 'aankoopdatum ' + reason + '. Geen import uitgevoerd.')
    }
    if (seen.has(id)) throw new Error('Dubbel Jumbo-bonnummer in de geschiedenislijst.')
    seen.add(id)
    if (day >= from && day <= to) selected.push(receipt)
  }
  if (selected.length > max) {
    throw new Error('Meer dan ' + max + ' Jumbo-bonnen in deze periode. Kies een kleinere periode.')
  }
  return selected
};
`

// Same validation as selectJumboHistory, with a global duplicate check.
const JUMBO_BOOKMARKLET_AUTO_PLANNER_SOURCE = String.raw`
const planJumboHistoricalBatches=function(receipts,from,to){
  jumboDateWindow(from,to);
  if(!Array.isArray(receipts)||receipts.length>JUMBO_MAX_PAGES*10)
    throw new Error("Jumbo-historie is te groot voor een volledige import.");
  const selected=[];const seen=new Set();
  for(let i=0;i<receipts.length;i+=JUMBO_BATCH_LIMIT){
    const checked=selectJumboHistory(receipts.slice(i,i+JUMBO_BATCH_LIMIT),from,to);
    for(const r of checked){
      if(seen.has(r.transactionId))throw new Error("Dubbel Jumbo-bonnummer over historiepagina’s.");
      seen.add(r.transactionId);selected.push(r);
    }
  }
  selected.sort((a,b)=>jumboDay(a.purchaseEndOn).localeCompare(jumboDay(b.purchaseEndOn))||
    a.transactionId.localeCompare(b.transactionId));
  const groups=[];
  for(const r of selected){
    const month=jumboDay(r.purchaseEndOn).slice(0,7);
    const last=groups[groups.length-1];
    if(!last||last.month!==month||last.receipts.length===JUMBO_BATCH_LIMIT)
      groups.push({month,receipts:[r]});
    else last.receipts.push(r);
  }
  return groups;
};
`

// A mobile opener can receive the entire history in strictly acknowledged
// ten-receipt batches. Desktop keeps the historical explicit-confirmation flow.
const JUMBO_AUTO_RUNNER_SOURCE = String.raw`
const history=[];let totalResults=null;let finished=false;
for(let page=0;page<MAX_PAGES;page++){
  show("Jumbo-historie: pagina "+String(page+1));
  const list=await gql("GetOnlineOrdersAndStoreReceipts",listQuery,{
    ordersInput:{offset:0,limit:1,direction:"DESC",sortBy:"deliveryDate",statusCategory:"CLOSED"},
    page,pageSize:10
  });
  const result=list.storeReceipts||{};
  if(!Array.isArray(result.receipts))throw new Error("Jumbo gaf geen geldige geschiedenispagina terug.");
  const count=Number(result.totalResults);
  if(!Number.isSafeInteger(count)||count<0||count>MAX_PAGES*10)
    throw new Error("Jumbo heeft meer geschiedenis dan veilig kan worden gecontroleerd; geen volledige import bevestigd.");
  if(totalResults===null)totalResults=count;
  if(count!==totalResults||Number(result.currentPage)!==page)
    throw new Error("Jumbo-historie of paginering veranderde tijdens ophalen; start opnieuw.");
  history.push(...result.receipts);
  if(history.length>=totalResults){finished=true;break;}
  if(!result.receipts.length)throw new Error("Jumbo gaf een lege tussenpagina terug.");
}
if(!finished||history.length!==totalResults)
  throw new Error("Jumbo-historie is onvolledig; geen periode afgesloten.");
const batches=planJumboHistoricalBatches(history,RANGE.from_date,RANGE.to_date);
const total=batches.reduce((n,b)=>n+b.receipts.length,0);
const detailQuery="query GetDigitalReceipt($transactionId: String) { receipt(transactionId: $transactionId) { receiptImage { image type receiptPoints { earned newBalance oldBalance redeemed } } store { name location { address { city houseNumber postalCode street } } } purchaseEndOn receiptSource transactionId } }";
const opener=window.opener;
if(!opener)throw new Error("Het Inhuis-tabblad is niet langer verbonden.");
async function sendBatch(details,index){
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{cleanup();reject(new Error("Inhuis bevestigde deelimport niet; later veilig opnieuw proberen."));},60000);
    function cleanup(){clearTimeout(timer);window.removeEventListener("message",receive);}
    function receive(event){
      const d=event.data;
      if(event.origin!==O||event.source!==opener||!d||d.type!=="inhuis:jumbo-ack"||
         d.request_id!==Q||d.index!==index||d.version!==V)return;
      cleanup();
      if(d.ok===true)resolve();
      else reject(new Error(String(d.error||"Jumbo-deelimport niet veilig ontvangen.")));
    }
    window.addEventListener("message",receive);
    opener.postMessage({type:"inhuis:jumbo-batch",request_id:Q,version:V,
      source_origin:location.origin,date_range:RANGE,index,total_batches:batches.length,details},O);
  });
}
let imported=0;
for(let index=0;index<batches.length;index++){
  const group=batches[index];
  show("Jumbo "+group.month+": deel "+String(index+1)+"/"+String(batches.length)+
    " ("+String(imported)+"/"+String(total)+" bonnen)");
  const details=[];
  for(const row of group.receipts){
    const transactionId=String(row.transactionId||"");
    const detailData=await gql("GetDigitalReceipt",detailQuery,{transactionId});
    const receipt=detailData.receipt;
    if(!receipt||String(receipt.transactionId||"")!==transactionId ||
       jumboDay(receipt.purchaseEndOn)!==jumboDay(row.purchaseEndOn))
       throw new Error("Jumbo-detailidentiteit of datum wijkt af van de historie.");
    const image=receipt.receiptImage||{};
    const parsed=parseReceipt(image.image);
    if(parsed.parseError)throw new Error("Jumbo-bonlayout kon niet worden ontleed.");
    details.push({transactionId,purchaseEndOn:receipt.purchaseEndOn,
      receiptSource:receipt.receiptSource||null,storeName:receipt.store?.name||null,
      receiptImageType:image.type||null,parsed});
  }
  await sendBatch(details,index);
  imported+=details.length;
}
opener.postMessage({type:"inhuis:jumbo-complete",request_id:Q,version:V,
 source_origin:location.origin,date_range:RANGE,count:imported,batches:batches.length},O);
show("Jumbo: "+String(imported)+" bonnen veilig aangeboden; Inhuis controleert verwerking.");
`

export function buildJumboPocBookmarklet(inhuisCallbackUrl, dateRange, options = {}) {
  const callbackUrl = String(inhuisCallbackUrl || '').replace(/#.*$/, '')
  if (!validInhuisCallbackUrl(callbackUrl)) {
    throw new Error('Ongeldige Inhuis-callback voor Jumbo-POC')
  }

  const range = dateRange || (() => {
    const now = new Date()
    const end = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    const start = new Date(end)
    start.setDate(start.getDate() - 29)
    const toDay = (d) => [d.getFullYear(), String(d.getMonth() + 1).padStart(2, '0'), String(d.getDate()).padStart(2, '0')].join('-')
    return { from_date: toDay(start), to_date: toDay(end) }
  })()
  const checkedRange = jumboDateWindow(range.from_date, range.to_date)
  const automatic = options.automatic === true
  const requestId = String(options.requestId || '')
  const openerOrigin = String(options.inhuisOrigin || '')
  if (automatic && (!/^[A-Za-z0-9-]{15,72}$/.test(requestId) ||
      !/^https?:\\/\\/[^/]+$/.test(openerOrigin) ||
      !callbackUrl.startsWith(openerOrigin + '/'))) {
    throw new Error('Jumbo-automatisering mist een geldige Inhuis-handshake.')
  }

  const bookmarkletSource = (
    '(async()=>{' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const C=' + JSON.stringify(callbackUrl) + ';' +
    'const P=' + JSON.stringify(JUMBO_POC_FRAGMENT_PREFIX) + ';' +
    'const AUTO=' + JSON.stringify(automatic) + ';' +
    'const O=' + JSON.stringify(openerOrigin) + ';' +
    'const Q=' + JSON.stringify(requestId) + ';' +
    JUMBO_BOOKMARKLET_PARSER_SOURCE + ';' +
    'const JUMBO_BATCH_LIMIT=' + String(JUMBO_BATCH_LIMIT) + ';' +
    JUMBO_BOOKMARKLET_HELPER_SOURCE +
    JUMBO_BOOKMARKLET_AUTO_PLANNER_SOURCE +
    'const RANGE=' + JSON.stringify(checkedRange) + ';' +
    'const LIMIT=' + String(JUMBO_BATCH_LIMIT) + ';' +
    'const MAX_PAGES=' + String(JUMBO_MAX_PAGES) + ';' +
    'const JUMBO_MAX_PAGES=' + String(JUMBO_MAX_PAGES) + ';' +
    'const ID="__inhuis_jumbo_redirect_poc";' +
    'let box=document.getElementById(ID);' +
    'if(!box){box=document.createElement("div");box.id=ID;box.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:520px;padding:12px 14px;background:#fff;border:2px solid currentColor;color:#111;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);white-space:pre-wrap";document.documentElement.appendChild(box);}' +
    'const show=m=>{box.textContent="Inhuis Jumbo receipt-POC\\n"+m;try{console.info("[Inhuis Jumbo receipt-POC]",m);}catch{}};' +
    'const ret=o=>{if(AUTO){if(window.opener)window.opener.postMessage({type:"inhuis:jumbo-error",request_id:Q,version:V,source_origin:location.origin,error:String(o.error||"Jumbo-import afgebroken.")},O);return;}show("Resultaat gereed; terug naar Inhuis…");if(encodeURIComponent(JSON.stringify(o)).length>48000)o={version:V,ok:false,source_origin:location.origin,error:"Te veel bongegevens voor veilige overdracht. Kies een kortere Jumbo-periode."};location.href=C+P+encodeURIComponent(JSON.stringify(o));};' +
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
    (automatic ? JUMBO_AUTO_RUNNER_SOURCE : "const history=[];let totalResults=null;let finished=false;\nfor(let page=0;page<MAX_PAGES;page++){\nshow(\"Jumbo geschiedenis ophalen: pagina \"+String(page+1));\nconst list=await gql(\"GetOnlineOrdersAndStoreReceipts\",listQuery,{ordersInput:{offset:0,limit:1,direction:\"DESC\",sortBy:\"deliveryDate\",statusCategory:\"CLOSED\"},page,pageSize:10});\nconst s=list.storeReceipts||{};const receipts=s.receipts;\nif(!Array.isArray(receipts))throw new Error(\"Jumbo gaf geen geldige geschiedenis terug.\");\nconst count=Number(s.totalResults);\nif(!Number.isSafeInteger(count)||count<0||count>300)throw new Error(\"Jumbo-bonnenaantal buiten veilige limiet.\");\nif(totalResults===null)totalResults=count;\nif(count!==totalResults)throw new Error(\"Jumbo-bonnenlijst is tijdens ophalen veranderd.\");\nif(Number(s.currentPage)!==page)throw new Error(\"Jumbo-paginering wijkt af.\");\nhistory.push(...receipts);\nif(history.length>=totalResults){finished=true;break;}\nif(!receipts.length)throw new Error(\"Jumbo retourneerde een lege tussenpagina.\");\n}\nif(!finished)throw new Error(\"Jumbo-geschiedenis heeft meer paginas dan veilig toegestaan.\");\nconst selected=selectJumboHistory(history,RANGE.from_date,RANGE.to_date,LIMIT);\nif(!selected.length){ret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,date_range:RANGE,details:[],first_detail:null});return;}\nconst detailQuery=\"query GetDigitalReceipt($transactionId: String) { receipt(transactionId: $transactionId) { receiptImage { image type receiptPoints { earned newBalance oldBalance redeemed } } store { name location { address { city houseNumber postalCode street } } } purchaseEndOn receiptSource transactionId } }\";\nconst details=[];\nfor(const row of selected){\nconst transactionId=String(row.transactionId||\"\");\nshow(\"Jumbo-bondetail \"+String(details.length+1)+\"/\"+String(selected.length));\nconst detailData=await gql(\"GetDigitalReceipt\",detailQuery,{transactionId});\nconst receipt=detailData.receipt;\nif(!receipt||String(receipt.transactionId||\"\")!==transactionId)throw new Error(\"Jumbo-detail komt niet overeen met historiebon.\");\nif(jumboDay(receipt.purchaseEndOn)!==jumboDay(row.purchaseEndOn))throw new Error(\"Jumbo-bondatum verschilt van historiedatum.\");\nconst image=receipt.receiptImage||{};const parsed=parseReceipt(image.image);\nif(parsed.parseError)throw new Error(\"Jumbo-bonlayout kon niet worden ontleed.\");\ndetails.push({transactionId,purchaseEndOn:receipt.purchaseEndOn,receiptSource:receipt.receiptSource||null,storeName:receipt.store?.name||null,receiptImageType:image.type||null,parsed});\n}\nret({version:V,ok:true,source_origin:location.origin,total_results:totalResults,date_range:RANGE,details,first_detail:details[0]||null});") +
    '}catch(err){' +
    'const message=String(err&&err.message?err.message:err);' +
    'show("POC-fout: "+message);' +
    'ret({version:V,ok:false,source_origin:location.origin,error:message});' +
    '}' +
    '})()'
  )
  // Firefox strips literal CR/LF/TAB from javascript: bookmark URL text before
  // evaluation, which joins statements such as `let data` and `try`.
  // Encode the JavaScript payload so whitespace survives URL normalization.
  return 'javascript:' + encodeURIComponent(bookmarkletSource)
}
