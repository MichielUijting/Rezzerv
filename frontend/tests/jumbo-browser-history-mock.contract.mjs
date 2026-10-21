import assert from 'node:assert/strict'
import vm from 'node:vm'
import { buildJumboPocBookmarklet, JUMBO_POC_FRAGMENT_PREFIX } from '../src/features/storeConnections/jumboReceiptPocBridge.js'

const receiptLayout = JSON.stringify({
  documents: [{ documents: [{ printSections: [{ textObjects: [{
    textLines: [
      { texts: [{ text: 'OMSCHRIJVING' }, { text: 'BEDRAG' }] },
      { texts: [{ text: 'BROOD' }, { text: '2,49' }] },
      { texts: [{ text: 'Totaal' }, { text: '2,49' }] },
    ],
  }] }] }] }],
})

const history = Array.from({ length: 12 }, (_, i) => ({
  transactionId: 'JUMBO-TEST-' + String(i).padStart(3, '0'),
  purchaseEndOn: i < 2 ? '2026-10-11T12:00:00' : '2026-09-01T12:00:00',
}))

async function runMock({ mutatePage = null, sourceHistory = history } = {}) {
  const calls = []
  let target = ''
  const context = {
    URL,
    console: { info: () => {} },
    location: {
      origin: 'https://www.jumbo.com',
      get href() { return target },
      set href(value) { target = value },
    },
    document: {
      getElementById: () => null,
      createElement: () => ({ style: {}, textContent: '' }),
      documentElement: { appendChild: () => {} },
    },
    fetch: async (url, options) => {
      assert.equal(url, '/api/graphql')
      assert.equal(options.credentials, 'include')
      const body = JSON.parse(options.body)
      calls.push(body.operationName)
      if (body.operationName === 'GetOnlineOrdersAndStoreReceipts') {
        const page = body.variables.page
        let response = {
          totalResults: sourceHistory.length,
          currentPage: page,
          pageSize: 10,
          receipts: sourceHistory.slice(page * 10, page * 10 + 10),
        }
        if (mutatePage) response = mutatePage(response, page)
        return { ok: true, json: async () => ({ data: { storeReceipts: response } }) }
      }
      assert.equal(body.operationName, 'GetDigitalReceipt')
      const record = sourceHistory.find(x => x.transactionId === body.variables.transactionId)
      return { ok: true, json: async () => ({
        data: { receipt: {
          ...record,
          store: { name: 'Jumbo testfiliaal' },
          receiptImage: { type: 'print', image: receiptLayout },
        } },
      }) }
    },
  }
  const script = buildJumboPocBookmarklet('http://localhost:5176/instellingen/winkelkoppelingen', {
    from_date: '2026-10-10', to_date: '2026-10-12',
  })
  await vm.runInNewContext(decodeURIComponent(script.replace(/^javascript:/, '')), context)
  assert.ok(target.includes(JUMBO_POC_FRAGMENT_PREFIX), 'redirect fragment must be produced')
  const result = JSON.parse(decodeURIComponent(target.split(JUMBO_POC_FRAGMENT_PREFIX)[1]))
  return { result, calls }
}

const ok = await runMock()
assert.equal(ok.result.ok, true, JSON.stringify(ok.result))
assert.equal(ok.result.total_results, 12)
assert.equal(ok.result.details.length, 2)
assert.equal(ok.result.details[0].parsed.items[0].name, 'BROOD')
assert.equal(ok.result.details[0].parsed.total, 2.49)
assert.deepEqual(ok.calls, [
  'GetOnlineOrdersAndStoreReceipts', 'GetOnlineOrdersAndStoreReceipts',
  'GetDigitalReceipt', 'GetDigitalReceipt',
])
const empty = await runMock({ sourceHistory: [] })
assert.equal(empty.result.ok, true)
assert.deepEqual(empty.result.details, [])
assert.deepEqual(empty.calls, ['GetOnlineOrdersAndStoreReceipts'])
const invalidPage = await runMock({
  mutatePage: (row, page) => ({ ...row, currentPage: page + 1 }),
})
assert.equal(invalidPage.result.ok, false)
assert.match(invalidPage.result.error, /paginering/)
const tooMany = await runMock({
  sourceHistory: history.map(x => ({ ...x, purchaseEndOn: '2026-10-11T12:00:00' })),
})
assert.equal(tooMany.result.ok, false)
assert.match(tooMany.result.error, /Meer dan 10 Jumbo-bonnen/)
const badId = await runMock({
  sourceHistory: [{ transactionId: 'PRIVATE WITH SPACE', purchaseEndOn: '2026-10-11T12:00:00' }],
})
assert.equal(badId.result.ok, false)
assert.match(badId.result.error, /regel 1: bonnummer heeft een onverwacht formaat/)
assert.doesNotMatch(badId.result.error, /PRIVATE WITH SPACE/)
assert.match(badId.result.error, /spaties of witruimte/)
const separatorId = await runMock({
  sourceHistory: [{ transactionId: 'JUMBO:TEST/2026.10', purchaseEndOn: '2026-10-11T12:00:00' }],
})
assert.equal(separatorId.result.ok, true, JSON.stringify(separatorId.result))
assert.equal(separatorId.result.details[0].transactionId, 'JUMBO:TEST/2026.10')
const missingDate = await runMock({
  sourceHistory: [{ transactionId: 'JUMBO-TEST-1', purchaseEndOn: null }],
})
assert.equal(missingDate.result.ok, false)
assert.match(missingDate.result.error, /regel 1: aankoopdatum ontbreekt of is ongeldig/)
console.log('JUMBO_PAGINATED_BROWSER_MOCK_GREEN')
