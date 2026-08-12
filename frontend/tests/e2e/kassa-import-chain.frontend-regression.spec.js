import { test, expect } from '@playwright/test'
import { API_URL, DEMO_HOUSEHOLD_ID } from './helpers/devApi.js'

const RUN_TOKEN = `${Date.now()}-${process.pid}`
let firstReceiptId = ''

function addJpegRegressionComment(buffer, label) {
  if (!Buffer.isBuffer(buffer) || buffer.length < 4 || buffer[0] !== 0xff || buffer[1] !== 0xd8) {
    throw new Error('Canonieke Kassa-regressiefixture is geen geldige JPEG.')
  }
  const comment = Buffer.from(`Rezzerv Kassa regressie ${RUN_TOKEN} ${label}`, 'utf8')
  const segmentLength = comment.length + 2
  if (segmentLength > 0xffff) throw new Error('JPEG-regressiecommentaar is te lang.')
  const marker = Buffer.from([0xff, 0xfe, (segmentLength >> 8) & 0xff, segmentLength & 0xff])
  return Buffer.concat([buffer.subarray(0, 2), marker, comment, buffer.subarray(2)])
}

async function loadCanonicalImageFixture(request, kind, label) {
  const response = await request.get(`${API_URL}/api/testing/fixtures/receipt/file?kind=${encodeURIComponent(kind)}`)
  expect(response.ok(), `Canonieke kassabonfixture '${kind}' moet beschikbaar zijn.`).toBeTruthy()
  const source = await response.body()
  return {
    name: `regressie-bon-kassa-${label}-${RUN_TOKEN}.jpg`,
    mimeType: 'image/jpeg',
    buffer: addJpegRegressionComment(source, label),
  }
}

async function uploadThroughKassaUi(page, file) {
  await page.goto('/kassa/nieuw')
  await expect(page.getByTestId('kassa-add-page')).toBeVisible()
  await expect(page.getByTestId('kassa-manual-file-input')).toHaveCount(1)

  const responsePromise = page.waitForResponse(
    (response) => {
      try {
        return new URL(response.url()).pathname === '/api/receipts/import'
          && response.request().method() === 'POST'
      } catch {
        return false
      }
    },
    { timeout: 120_000 },
  )

  await page.getByTestId('kassa-manual-file-input').setInputFiles(file)
  const response = await responsePromise
  const text = await response.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    throw new Error(`Kassa-import gaf geen geldige JSON terug: HTTP ${response.status()} ${text.slice(0, 500)}`)
  }

  expect([200, 201], `Kassa-import moet HTTP 200/201 geven; payload=${JSON.stringify(payload)}`).toContain(response.status())
  return { response, payload }
}

async function fetchReceiptsInBrowser(page) {
  return page.evaluate(async (householdId) => {
    const response = await fetch(`/api/receipts?householdId=${encodeURIComponent(householdId)}`, { credentials: 'include' })
    const text = await response.text()
    let payload = null
    try { payload = text ? JSON.parse(text) : null } catch { payload = text }
    return { status: response.status, payload }
  }, String(DEMO_HOUSEHOLD_ID))
}

async function fetchReceiptDetailInBrowser(page, receiptId) {
  return page.evaluate(async (id) => {
    const response = await fetch(`/api/receipts/${encodeURIComponent(id)}`, { credentials: 'include' })
    const text = await response.text()
    let payload = null
    try { payload = text ? JSON.parse(text) : null } catch { payload = text }
    return { status: response.status, payload }
  }, receiptId)
}

function resolveReceiptId(payload) {
  return String(payload?.receipt_table_id || payload?.receiptTableId || payload?.existing_receipt?.receipt_table_id || '')
}

async function expectSingleLogicalReceipt(page, receiptId) {
  const listResult = await fetchReceiptsInBrowser(page)
  expect(listResult.status).toBe(200)
  const items = Array.isArray(listResult.payload?.items) ? listResult.payload.items : []
  expect(items.filter((item) => String(item?.receipt_table_id || '') === String(receiptId))).toHaveLength(1)
  return items
}

test.describe('Kassa echte importketen frontend-regressie', () => {
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(180_000)

  test('bekende kassabon wordt via echte Kassa-upload ingelezen en inhoudelijk zichtbaar', async ({ page, request }) => {
    const fixture = await loadCanonicalImageFixture(request, 'manual', 'eerste')
    const { payload } = await uploadThroughKassaUi(page, fixture)

    expect(payload?.duplicate).not.toBe(true)
    expect(payload?.batch).not.toBe(true)
    firstReceiptId = resolveReceiptId(payload)
    expect(firstReceiptId, `Nieuwe import moet receipt_table_id teruggeven: ${JSON.stringify(payload)}`).not.toBe('')

    await page.goto('/kassa')
    await expect(page.getByTestId(`kassa-row-${firstReceiptId}`)).toBeVisible({ timeout: 30_000 })
    await expectSingleLogicalReceipt(page, firstReceiptId)

    const detail = await fetchReceiptDetailInBrowser(page, firstReceiptId)
    expect(detail.status).toBe(200)
    expect(Array.isArray(detail.payload?.lines)).toBeTruthy()
    expect(detail.payload.lines.length).toBeGreaterThan(0)
    expect(String(detail.payload?.store_name || '')).not.toBe('')
  })

  test('ingelezen kassabon blijft na volledige browserreload leesbaar vanuit Kassa', async ({ page }) => {
    expect(firstReceiptId, 'De eerste seriële Kassa-import moet een bon-id hebben opgeleverd.').not.toBe('')

    await page.goto('/kassa')
    await page.reload()
    const row = page.getByTestId(`kassa-row-${firstReceiptId}`)
    await expect(row).toBeVisible({ timeout: 30_000 })
    await row.dblclick()

    await expect(page.getByRole('tab', { name: 'Bonregels', exact: true })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId('receipt-lines-table')).toBeVisible({ timeout: 20_000 })

    const detail = await fetchReceiptDetailInBrowser(page, firstReceiptId)
    expect(detail.status).toBe(200)
    expect(Array.isArray(detail.payload?.lines)).toBeTruthy()
    expect(detail.payload.lines.length).toBeGreaterThan(0)
  })

  test('dezelfde kassabon opnieuw inlezen wordt als duplicate herkend zonder tweede logisch bonrecord', async ({ page, request }) => {
    expect(firstReceiptId, 'De eerste seriële Kassa-import moet een bon-id hebben opgeleverd.').not.toBe('')
    const fixture = await loadCanonicalImageFixture(request, 'manual', 'eerste')
    const { response, payload } = await uploadThroughKassaUi(page, fixture)

    expect(response.status()).toBe(200)
    expect(payload?.duplicate).toBe(true)
    const duplicateReceiptId = resolveReceiptId(payload)
    expect(duplicateReceiptId).toBe(firstReceiptId)

    await expectSingleLogicalReceipt(page, firstReceiptId)
    await expect(page.locator('body')).toContainText(/al ingelezen|al eerder toegevoegd|niet opnieuw geladen/i, { timeout: 20_000 })

    await page.goto('/kassa')
    await expect(page.getByTestId(`kassa-row-${firstReceiptId}`)).toBeVisible({ timeout: 30_000 })
    const detail = await fetchReceiptDetailInBrowser(page, firstReceiptId)
    expect(detail.status).toBe(200)
    expect(Array.isArray(detail.payload?.lines)).toBeTruthy()
    expect(detail.payload.lines.length).toBeGreaterThan(0)
  })

  test('een tweede andere kassabon kan direct daarna via dezelfde Kassa-flow worden ingelezen', async ({ page, request }) => {
    expect(firstReceiptId, 'De eerste seriële Kassa-import moet een bon-id hebben opgeleverd.').not.toBe('')
    const secondFixture = await loadCanonicalImageFixture(request, 'camera', 'tweede')
    const { payload } = await uploadThroughKassaUi(page, secondFixture)

    expect(payload?.duplicate).not.toBe(true)
    expect(payload?.batch).not.toBe(true)
    const secondReceiptId = resolveReceiptId(payload)
    expect(secondReceiptId, `Tweede import moet receipt_table_id teruggeven: ${JSON.stringify(payload)}`).not.toBe('')
    expect(secondReceiptId).not.toBe(firstReceiptId)

    await page.goto('/kassa')
    await expect(page.getByTestId(`kassa-row-${firstReceiptId}`)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByTestId(`kassa-row-${secondReceiptId}`)).toBeVisible({ timeout: 30_000 })

    const items = await expectSingleLogicalReceipt(page, secondReceiptId)
    expect(items.filter((item) => [firstReceiptId, secondReceiptId].includes(String(item?.receipt_table_id || '')))).toHaveLength(2)

    const secondDetail = await fetchReceiptDetailInBrowser(page, secondReceiptId)
    expect(secondDetail.status).toBe(200)
    expect(Array.isArray(secondDetail.payload?.lines)).toBeTruthy()
    expect(secondDetail.payload.lines.length).toBeGreaterThan(0)
  })
})
