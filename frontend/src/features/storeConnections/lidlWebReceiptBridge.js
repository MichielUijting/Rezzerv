export const LIDL_WEB_ORIGIN = 'https://www.lidl.nl'

export const LIDL_HISTORY_URL =
  'https://www.lidl.nl/mre/purchase-history?client_id=NetherlandsEcommerceClient&country_code=nl&language=nl-NL&page=1'

function lidlWebPageRunner(INHUIS_ORIGIN) {
  const target = window.open('', 'inhuis-lidl-import')
  if (!target) {
    alert('Het Inhuis-importvenster is niet beschikbaar.')
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

  function parseReceipt(doc, receiptId, fallback = {}) {
    const pre = doc.querySelector('[data-testid="ticket-' + CSS.escape(receiptId) + '"] pre')
    if (!pre) throw new Error('Lidl-bon ' + receiptId + ' kon niet worden gelezen')

    const grouped = new Map()
    for (const span of pre.querySelectorAll('.purchase_list span[id], span[id][data-art-description]')) {
      const key = span.id || ('row-' + grouped.size)
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key).push(span)
    }

    const products = []
    let current = null
    for (const spans of grouped.values()) {
      const first = spans[0]
      const text = spans.map((span) => span.textContent || '').join('').replace(/\u00a0/g, ' ')
      const data = first.dataset || {}
      const amountMatch = text.match(/(-?\d+[,.]\d{2})\s*[A-Z]?\s*$/)
      const amount = amountMatch ? amountMatch[1] : null
      const description = clean(data.artDescription)

      if (description) {
        current = {
          name: description,
          quantity: data.artQuantity || '1',
          unitPrice: data.unitPrice || null,
          lineTotal: amount,
          articleId: data.artId || null,
          taxType: data.taxType || null,
          discounts: [],
        }
        products.push(current)
      } else if (current && amount && String(amount).startsWith('-')) {
        current.discounts.push({
          description: clean(text.replace(amount, '')) || 'Korting',
          amount: String(amount).replace('-', ''),
        })
      }
    }

    if (!products.length) {
      throw new Error('Geen gestructureerde artikelregels gevonden op Lidl-bon ' + receiptId)
    }

    for (const product of products) {
      if (!product.discounts.length) continue
      const discountTotal = product.discounts.reduce((sum, discount) => {
        const value = Number(String(discount.amount || '0').replace(',', '.'))
        return sum + (Number.isFinite(value) ? value : 0)
      }, 0)
      product.discountAmount = discountTotal.toFixed(2)
    }

    const receiptText = pre.textContent || ''
    const totalMatch =
      receiptText.match(/Totaal\s+(-?\d+[,.]\d{2})/i) ||
      receiptText.match(/Zu zahlen\s+(-?\d+[,.]\d{2})/i)

    const detailStore = clean(doc.querySelector('[data-testid="store"] [class*="_title_"]')?.textContent)
    const storeName = detailStore || clean(fallback.store) || 'Lidl'

    return {
      id: receiptId,
      dateTime: parseDateTime(receiptText, fallback.date || ''),
      totalAmount: clean((totalMatch && totalMatch[1]) || fallback.amount || '').replace('€', '').trim(),
      store: { name: storeName, city: storeName },
      products,
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
  const target = origin + '/instellingen/winkelkoppelingen?lidlImport=1'
  return (
    'javascript:(()=>{' +
    'const O=' + JSON.stringify(origin) + ';' +
    'const W=window.open(' + JSON.stringify(target) + ',"inhuis-lidl-import");' +
    'if(!W){alert("Sta pop-ups toe om Lidl-bonnen naar Inhuis te sturen.");return;}' +
    'window.addEventListener("message",e=>{' +
    'if(e.origin!==O||e.source!==W||!e.data||e.data.type!=="inhuis:lidl-script")return;' +
    'try{new Function(e.data.script)();}catch(err){alert("Lidl-import kon niet starten: "+String(err&&err.message||err));}' +
    '},{once:true});' +
    '})()'
  )
}

export function buildLidlWebPageScript(inhuisOrigin) {
  const origin = String(inhuisOrigin || '').replace(/\/$/, '')
  return '(' + lidlWebPageRunner.toString() + ')(' + JSON.stringify(origin) + ')'
}
