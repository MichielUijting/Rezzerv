export const JUMBO_BOOKMARKLET_VERSION = 4
export const JUMBO_ORDERS_URL = 'https://www.jumbo.com/bestellingen'
export const JUMBO_POC_FRAGMENT_PREFIX = '#jumbo-poc-v4='

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

export function buildJumboPocBookmarklet(inhuisCallbackUrl) {
  const callbackUrl = String(inhuisCallbackUrl || '').replace(/#.*$/, '')
  if (!validInhuisCallbackUrl(callbackUrl)) {
    throw new Error('Ongeldige Inhuis-callback voor Jumbo-POC')
  }

  return (
    'javascript:(async()=>{' +
    'const V=' + String(JUMBO_BOOKMARKLET_VERSION) + ';' +
    'const C=' + JSON.stringify(callbackUrl) + ';' +
    'const P=' + JSON.stringify(JUMBO_POC_FRAGMENT_PREFIX) + ';' +
    'const ID="__inhuis_jumbo_redirect_poc";' +
    'let box=document.getElementById(ID);' +
    'if(!box){box=document.createElement("div");box.id=ID;box.style.cssText="position:fixed;z-index:2147483647;right:12px;bottom:12px;max-width:520px;padding:12px 14px;background:#fff;border:2px solid #005F6A;color:#111;font:14px/1.4 Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);white-space:pre-wrap";document.documentElement.appendChild(box);}' +
    'const show=m=>{box.textContent="Inhuis Jumbo redirect-POC\\n"+m;try{console.info("[Inhuis Jumbo redirect-POC]",m);}catch{}};' +
    'const ret=o=>{show("Resultaat gereed; terug naar Inhuis…");location.href=C+P+encodeURIComponent(JSON.stringify(o));};' +
    'try{' +
    'show("Stap 1/3: Jumbo GraphQL bonnenlijst opvragen…");' +
    'const q="query GetOnlineOrdersAndStoreReceipts($ordersInput: OrdersInput!, $page: Int, $pageSize: Int) { storeReceipts: receiptOverview(page: $page, pageSize: $pageSize) { totalResults pageSize currentPage receipts { transactionId purchaseEndOn receiptSource store { storeId name } } } onlineOrders: orders(input: $ordersInput) { totalCount } }";' +
    'const r=await fetch("/api/graphql",{method:"POST",credentials:"include",headers:{"Content-Type":"application/json",Accept:"application/json","apollographql-client-name":"JUMBO_WEB-orders","apollographql-client-version":"master-v29.2.0-web","x-source":"JUMBO_WEB-orders"},body:JSON.stringify({operationName:"GetOnlineOrdersAndStoreReceipts",query:q,variables:{ordersInput:{offset:0,limit:1,direction:"DESC",sortBy:"deliveryDate",statusCategory:"CLOSED"},page:0,pageSize:10}})});' +
    'const j=await r.json().catch(()=>null);' +
    'if(!r.ok)throw new Error("Jumbo GraphQL HTTP "+r.status);' +
    'if(!j||typeof j!=="object")throw new Error("Jumbo GraphQL gaf geen geldig JSON-antwoord");' +
    'if(Array.isArray(j.errors)&&j.errors.length)throw new Error(String(j.errors[0]?.message||"Jumbo GraphQL-fout"));' +
    'const s=j.data?.storeReceipts||{};' +
    'const receipts=Array.isArray(s.receipts)?s.receipts:[];' +
    'show("Stap 2/3: GraphQL gelukt; "+String(Number(s.totalResults||receipts.length||0))+" bon(nen) gevonden.");' +
    'ret({version:V,ok:true,source_origin:location.origin,total_results:Number(s.totalResults||receipts.length||0),current_page:Number(s.currentPage||0),sample_receipt:receipts[0]?{transactionId:String(receipts[0]?.transactionId||""),purchaseEndOn:receipts[0]?.purchaseEndOn||null,receiptSource:receipts[0]?.receiptSource||null,storeName:receipts[0]?.store?.name||null}:null});' +
    '}catch(err){' +
    'const message=String(err&&err.message?err.message:err);' +
    'show("POC-fout: "+message);' +
    'ret({version:V,ok:false,source_origin:location.origin,error:message});' +
    '}' +
    '})()'
  )
}
