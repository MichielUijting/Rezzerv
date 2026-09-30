export const LIDL_WEB_ORIGIN = 'https://www.lidl.nl'
export const LIDL_BOOKMARKLET_VERSION = 2

export const LIDL_HISTORY_URL =
  'https://www.lidl.nl/mre/purchase-history?client_id=NetherlandsEcommerceClient&country_code=nl&language=nl-NL&page=1'

function lidlWebPageRunner(INHUIS_ORIGIN) {
  const target = window.opener
  if (!target) {
    alert('De bestaande Inhuis-sessie is niet meer beschikbaar. Open Lidl opnieuw via Inhuis > Winkelkoppelingen.')
    return
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim()

  function post(data) {
    target.postMessage(data, INHUIS_ORIGIN)
  }

  function receiptIdFromUrl(url) {
    try {
      return new URL(url, location.origin).searchParams.get('t') || ''
    } catch {
      return ''
    }
  }

  function waitForAck(receiptId, timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMessage)
        reject(new Error('Inhuis reageert niet op bon ' + receiptId))
      }, timeoutMs)
      function onMessage(event) {
        if (event.origin !== INHUIS_ORIGIN || event.source !== target) return
        if (!event.data || event.data.type !== 'inhuis:lidl-ack') return
        if (String(event.data.receipt_id || '') !== String(receiptId)) return
        clearTimeout(timer)
        window.removeEventListener('message', onMessage)
        if (event.data.ok) resolve(event.data)
        else reject(new Error(event.data.error || 'Import in Inhuis is mislukt'))
      }
      window.addEventListener('message', onMessage)
    })
  }

  function parseDateTime(text, fallbackDate = '') {
    const match = String(text || '').match(/(\d{2})[.\/-](\d{2})[.\/-](\d{2,4})\s+(\d{2}:\d{2})/)
    if (!match) return fallbackDate
    let year = match[3]
    if (year.length === 2) year = '20' + year
    return year + '-' + match[2] + '-' + match[1] + 'T' + match[4] + ':00'
  }

  function snapshotReceipt(pre) {
    const text = String(pre?.innerText || pre?.textContent || '')
    const lines = text.replace(/\r/g, '').split('\n')
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    if (!context) return ''

    const fontSize = 15
    const lineHeight = 20
    const padding = 28
    context.font = fontSize + 'px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    let widest = 0
    for (const line of lines) {
      widest = Math.max(widest, context.measureText(line || ' ').width)
    }

    canvas.width = Math.max(420, Math.min(1400, Math.ceil(widest + padding * 2)))
    canvas.height = Math.max(320, Math.min(16000, Math.ceil(lines.length * lineHeight + padding * 2)))

    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.fillStyle = '#111111'
    context.font = fontSize + 'px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
    context.textBaseline = 'top'

    let y = padding
    for (const line of lines) {
      if (y + lineHeight > canvas.height - padding) break
      context.fillText(line, padding, y)
      y += lineHeight
    }

    try {
      return canvas.toDataURL('image/png')
    } catch {
      return ''
    }
  }

  function numericAmount(value) {
    const cleaned = String(value || '').replace('€', '').replace(/\s+/g, '').replace(',', '.')
    const parsed = Number(cleaned)
    return Number.isFinite(parsed) ? parsed : null
  }

  function datasetIdentifier(data) {
    for (const key of ['gtin', 'ean', 'barcode', 'codeInput', 'productCode']) {
      const value = clean(data?.[key])
      if (value) return value
    }
    return null
  }

  function inferPackageSize(description, rawText) {
    const haystack = (String(description || '') + ' ' + String(rawText || '')).replace(',', '.')
    const multi = haystack.match(/\b(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(kg|g|l|ml|cl)\b/i)
    if (multi) return multi[1] + ' x ' + multi[2] + ' ' + multi[3].toLowerCase()
    const single = haystack.match(/\b(\d+(?:\.\d+)?)\s*(kg|g|l|ml|cl)\b/i)
    if (single) return single[1] + ' ' + single[2].toLowerCase()
    return null
  }

  function parseReceipt(doc, receiptId, fallback = {}) {
    const pre = doc.querySelector('[data-testid="ticket-' + CSS.escape(receiptId) + '"] pre')
    if (!pre) throw new Error('Lidl-bon ' + receiptId + ' kon niet worden gelezen')

    const grouped = new Map()
    let anonymousRowIndex = 0
    for (const span of pre.querySelectorAll('.purchase_list span[id], .purchase_list span[data-art-description]')) {
      const parentWithId = span.parentElement?.closest?.('[id]')
      const key = span.id || parentWithId?.id || ('row-anonymous-' + anonymousRowIndex++)
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key).push(span)
    }

    const vatByType = new Map()
    for (const span of pre.querySelectorAll('.vat_info span[data-tax-type]')) {
      const data = span.dataset || {}
      const taxType = clean(data.taxType)
      if (!taxType) continue
      vatByType.set(taxType, {
        type: taxType,
        percentage: clean(data.taxPercentage) || null,
        gross: clean(data.taxBaseAmount) || null,
        tax: clean(data.taxAmount) || null,
      })
    }

    const products = []
    let current = null
    for (const spans of grouped.values()) {
      const first = spans[0]
      const structuredArticleSpan =
        spans.find((span) => clean(span.dataset?.artDescription)) ||
        spans.find((span) => span.classList.contains('article')) ||
        first
      const text = spans.map((span) => span.textContent || '').join('').replace(/\u00a0/g, ' ')
      const data = structuredArticleSpan.dataset || {}
      const amountMatch = text.match(/(-?\d+[,.]\d{2})\s*[A-Z]?\s*$/)
      const amount = amountMatch ? amountMatch[1] : null
      const description = clean(data.artDescription)
      const isArticle = spans.some((span) => span.classList.contains('article')) || Boolean(description)

      if (isArticle && description) {
        const identifier = datasetIdentifier(data)
        const taxInfo = vatByType.get(clean(data.taxType)) || null
        const packageSize = inferPackageSize(description, text)
        current = {
          name: description,
          quantity: clean(data.artQuantity) || '1',
          unitPrice: clean(data.unitPrice) || null,
          grossAmount: amount,
          lineTotal: amount,
          articleId: clean(data.artId) || null,
          retailerSku: clean(data.artId) || null,
          taxType: clean(data.taxType) || null,
          taxRate: taxInfo?.percentage || null,
          taxAmount: null,
          unit: clean(data.unit || data.unitOfMeasure || data.uom) || packageSize || null,
          packageSize,
          rawText: clean(text),
          discounts: [],
        }
        if (identifier) {
          current.barcode = identifier
          current.codeInput = identifier
        }
        products.push(current)
        continue
      }

      if (current && isArticle && !description && !clean(data.artQuantity)) {
        const qtyMatch = text.match(/^\s*(\d+(?:[,.]\d+)?)\s*(?:Stk\.?|stuk|stuks?)?\s*x\b/i)
        const packageSize = inferPackageSize('', text)
        if (qtyMatch) current.quantity = qtyMatch[1].replace(',', '.')
        if (packageSize) {
          current.packageSize = packageSize
          if (!current.unit) current.unit = packageSize
        }
        if (qtyMatch || packageSize) continue
      }

      const lower = clean(text).toLowerCase()
      if (amount && /\b(statiegeld|deposit|pfand)\b/i.test(lower)) {
        products.push({
          name: clean(text.replace(amount, '')) || 'Statiegeld',
          quantity: '1',
          unitPrice: amount,
          grossAmount: amount,
          lineTotal: amount,
          lineType: 'deposit',
          rawText: clean(text),
          discounts: [],
        })
        current = null
        continue
      }

      if (current && amount && String(amount).startsWith('-')) {
        current.discounts.push({
          description: clean(text.replace(amount, '')) || 'Korting',
          amount: String(amount).replace('-', ''),
        })
      }
    }

    if (!products.length) {
      throw new Error('Geen gestructureerde artikelregels gevonden op Lidl-bon ' + receiptId)
    }

    let lineDiscountTotal = 0
    let depositTotal = 0
    for (const product of products) {
      const gross = numericAmount(product.grossAmount)
      if (product.lineType === 'deposit') {
        if (gross !== null) depositTotal += gross
        continue
      }
      const discountTotal = product.discounts.reduce((sum, discount) => {
        const value = numericAmount(discount.amount)
        return sum + (value === null ? 0 : Math.abs(value))
      }, 0)
      if (discountTotal > 0) {
        product.discountAmount = discountTotal.toFixed(2)
        lineDiscountTotal += discountTotal
        if (gross !== null) product.lineTotal = Math.max(0, gross - discountTotal).toFixed(2)
      }
    }

    const receiptText = pre.textContent || ''
    const expectedArticleCountMatch =
      receiptText.match(/Aantal\s+artikelen\s+(\d+)/i) ||
      receiptText.match(/Anzahl\s+Artikel\s+(\d+)/i)
    const expectedArticleCount = expectedArticleCountMatch
      ? Number.parseInt(expectedArticleCountMatch[1], 10)
      : null
    const extractedArticleQuantity = products
      .filter((product) => product.lineType !== 'deposit')
      .reduce((sum, product) => {
        const value = Number(String(product.quantity || '1').replace(',', '.'))
        return sum + (Number.isFinite(value) ? value : 1)
      }, 0)
    const totalMatch =
      receiptText.match(/Totaal\s+(-?\d+[,.]\d{2})/i) ||
      receiptText.match(/Zu zahlen\s+(-?\d+[,.]\d{2})/i)
    const receiptDiscountMatch =
      receiptText.match(/Totaal\s+(?:korting|prijsvoordeel)\s+(-?\d+[,.]\d{2})/i) ||
      receiptText.match(/Uw\s+voordeel\s+(-?\d+[,.]\d{2})/i)

    const receiptDiscountValue = numericAmount(receiptDiscountMatch?.[1])
    const discountTotal = receiptDiscountValue === null
      ? lineDiscountTotal
      : Math.abs(receiptDiscountValue)

    const detailStore = clean(doc.querySelector('[data-testid="store"] [class*="_title_"]')?.textContent)
    const storeName = detailStore || clean(fallback.store) || 'Lidl'
    const payment = clean(pre.querySelector('[data-tender-description]')?.dataset?.tenderDescription)
    const coupons = [...doc.querySelectorAll('[data-testid="coupons"] [class*="_item_"]')]
      .map((element) => clean(element.textContent))
      .filter(Boolean)

    const vat = [...vatByType.values()]

    return {
      id: receiptId,
      dateTime: parseDateTime(receiptText, fallback.date || ''),
      totalAmount: clean((totalMatch && totalMatch[1]) || fallback.amount || '').replace('€', '').trim(),
      discountTotal: discountTotal > 0 ? discountTotal.toFixed(2) : null,
      depositTotal: depositTotal > 0 ? depositTotal.toFixed(2) : null,
      paidTotal: clean((totalMatch && totalMatch[1]) || fallback.amount || '').replace('€', '').trim(),
      paymentMethod: payment || null,
      store: { name: storeName, city: storeName },
      products,
      vat,
      coupons,
      extractionDiagnostics: {
        structuredRowCount: grouped.size,
        extractedProductCount: products.filter((product) => product.lineType !== 'deposit').length,
        extractedArticleQuantity,
        expectedArticleCount,
        articleCountMatches:
          expectedArticleCount === null ? null : Math.abs(extractedArticleQuantity - expectedArticleCount) < 0.001,
      },
      _sourceSnapshotDataUrl: snapshotReceipt(pre),
      sourceUrl: location.origin + '/mre/purchase-detail?t=' + encodeURIComponent(receiptId),
    }
  }

  async function loadDetail(url, fallback) {
    const receiptId = receiptIdFromUrl(url)
    if (!receiptId) throw new Error('Lidl-bon heeft geen bonnummer')
    const iframe = document.createElement('iframe')
    iframe.style.cssText = 'position:fixed;left:-10000px;top:0;width:1200px;height:900px;border:0;opacity:0'
    document.body.appendChild(iframe)
    try {
      iframe.src = url
      const started = Date.now()
      while (Date.now() - started < 45000) {
        await sleep(250)
        try {
          const doc = iframe.contentDocument
          if (doc && doc.querySelector('[data-testid="ticket-' + CSS.escape(receiptId) + '"] pre')) {
            return parseReceipt(doc, receiptId, fallback)
          }
        } catch {}
      }
      throw new Error('Lidl-bon ' + receiptId + ' kon niet worden geladen')
    } finally {
      iframe.remove()
    }
  }

  async function collectHistory() {
    const all = []
    const seen = new Set()

    for (let pageNumber = 1; pageNumber <= 50; pageNumber += 1) {
      const url = new URL('/mre/purchase-history', location.origin)
      url.searchParams.set('client_id', 'NetherlandsEcommerceClient')
      url.searchParams.set('country_code', 'nl')
      url.searchParams.set('language', 'nl-NL')
      url.searchParams.set('page', String(pageNumber))

      const iframe = document.createElement('iframe')
      iframe.style.cssText = 'position:fixed;left:-10000px;top:0;width:1200px;height:900px;border:0;opacity:0'
      document.body.appendChild(iframe)
      let anchors = []
      try {
        iframe.src = url.href
        const started = Date.now()
        while (Date.now() - started < 30000) {
          await sleep(250)
          try {
            const doc = iframe.contentDocument
            anchors = doc ? [...doc.querySelectorAll('a[href*="/mre/purchase-detail"]')] : []
            if (anchors.length) break
          } catch {}
        }

        if (!anchors.length) break
        let added = 0
        for (const anchor of anchors) {
          const id = receiptIdFromUrl(anchor.href)
          if (!id || seen.has(id)) continue
          seen.add(id)
          added += 1
          const q = (testId) => clean(anchor.querySelector('[data-testid="' + testId + '"]')?.textContent)
          all.push({
            id,
            href: anchor.href,
            date: q('purchase-history-row-date'),
            store: q('purchase-history-row-store'),
            amount: q('primary-amount'),
          })
        }
        if (!added) break
      } finally {
        iframe.remove()
      }
    }

    return all
  }

  ;(async () => {
    try {
      post({ type: 'inhuis:lidl-progress', message: 'Lidl-bonnen zoeken…' })
      let entries = []

      if (location.pathname.includes('/mre/purchase-detail')) {
        entries = [{ id: receiptIdFromUrl(location.href), href: location.href, date: '', store: '', amount: '' }]
      } else if (location.pathname.includes('/mre/purchase-history')) {
        entries = await collectHistory()
      } else {
        throw new Error('Open eerst Mijn digitale kassabonnen of een Lidl-kassabon.')
      }

      if (!entries.length) throw new Error('Geen Lidl-kassabonnen gevonden.')

      let imported = 0
      for (const entry of entries) {
        post({
          type: 'inhuis:lidl-progress',
          message: 'Lidl-bon ' + (imported + 1) + ' van ' + entries.length + ' lezen…',
        })
        const receipt = await loadDetail(entry.href, entry)
        target.postMessage({ type: 'inhuis:lidl-receipt', receipt }, INHUIS_ORIGIN)
        await waitForAck(receipt.id)
        imported += 1
        post({
          type: 'inhuis:lidl-progress',
          message: imported + ' van ' + entries.length + ' bonnen verwerkt.',
        })
      }

      post({ type: 'inhuis:lidl-complete', count: imported })
      target.focus()
    } catch (error) {
      post({ type: 'inhuis:lidl-error', message: String(error && error.message ? error.message : error) })
      target.focus()
    }
  })()
}

export function buildLidlWebBookmarklet(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[[^\]]+\]|[^/]+)(:\d+)?$/i.test(origin)) {
    throw new Error('Ongeldige Inhuis-origin voor Lidl-import')
  }
  return (
    'javascript:(()=>{' +
    'const O=' + JSON.stringify(origin) + ';' +
    'const V=' + String(LIDL_BOOKMARKLET_VERSION) + ';' +
    'const W=window.opener;' +
    'if(!W){alert("Open Mijn Lidl-kassabonnen eerst vanuit Inhuis > Winkelkoppelingen. Laat dat Inhuis-tabblad open en gebruik daarna deze favoriet.");return;}' +
    'let done=false;' +
    'window.addEventListener("message",e=>{' +
    'if(done||e.origin!==O||e.source!==W||!e.data||e.data.type!=="inhuis:lidl-script")return;' +
    'done=true;' +
    'try{new Function(e.data.script)();}catch(err){alert("Lidl-import kon niet starten: "+String(err&&err.message||err));}' +
    '},{once:false});' +
    'W.postMessage({type:"inhuis:lidl-handshake",bookmarklet_version:V},O);' +
    'setTimeout(()=>{if(!done)alert("De bestaande Inhuis-sessie reageert niet. Open Lidl opnieuw via Inhuis > Winkelkoppelingen.");},4000);' +
    '})()'
  )
}

export function buildLidlWebPageScript(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  return '(' + lidlWebPageRunner.toString() + ')(' + JSON.stringify(origin) + ')'
}
