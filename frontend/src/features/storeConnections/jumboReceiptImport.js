// Jumbo browser data is untrusted: only an explicit, reconciled receipt may enter Kassa.
// This adapter never performs HTTP requests or stores credentials.
import { JUMBO_BOOKMARKLET_VERSION } from './jumboReceiptPocBridge.js'
import { jumboDay } from './jumboReceiptBatch.js'

export const JUMBO_WEB_ORIGIN = 'https://www.jumbo.com'

function moneyCents(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  const cents = Math.round(value * 100)
  return Math.abs(value * 100 - cents) < 0.001 ? cents : null
}

function validPurchaseDate(value) {
  return Boolean(jumboDay(value))
}

export function buildJumboImportEnvelope(payload) {
  if (!payload || payload.version !== JUMBO_BOOKMARKLET_VERSION || payload.ok !== true ||
      payload.source_origin !== JUMBO_WEB_ORIGIN) {
    throw new Error('De Jumbo-herkomst of de versie van de bon is ongeldig.')
  }
  const detail = payload.first_detail
  if (!detail) throw new Error('Er is geen digitale Jumbo-kassabon beschikbaar.')
  const transactionId = typeof detail.transactionId === 'string' ? detail.transactionId : ''
  if (!/^[\x21-\x7E]{4,100}$/.test(transactionId)) {
    throw new Error('Het Jumbo-bonnummer ontbreekt of is ongeldig.')
  }
  if (!validPurchaseDate(detail.purchaseEndOn)) {
    throw new Error('De datum van de Jumbo-bon ontbreekt of is ongeldig.')
  }
  const parsed = detail.parsed
  if (!parsed || parsed.parseError || !Array.isArray(parsed.items) || parsed.items.length === 0 ||
      parsed.items.length > 200 || !Array.isArray(parsed.deposits) || parsed.deposits.length > 50) {
    throw new Error('De Jumbo-bon bevat geen volledig herkenbare artikelregels.')
  }
  const lines = []
  let calculated = 0
  let discountCents = 0
  let depositCents = 0
  for (const item of [...parsed.items, ...parsed.deposits]) {
    const name = String(item?.name || '').trim()
    const lineCents = moneyCents(item?.price)
    const quantity = Number(item?.quantity)
    const unitCents = moneyCents(item?.unitPrice)
    if (!name || name.length > 240 || lineCents === null ||
        !Number.isSafeInteger(quantity) || quantity < 1 || quantity > 10000 ||
        unitCents === null) {
      throw new Error('Jumbo-bon bevat een ontbrekend of ongeldig artikelbedrag.')
    }
    const isDeposit = item.isDeposit === true
    const isDiscount = !isDeposit && /^(?:korting|actievoordeel|bonus)\b/i.test(name)
    if (!isDiscount && Math.abs(unitCents * quantity - lineCents) > 1) {
      throw new Error('Artikelbedrag en aantal sluiten niet op elkaar aan.')
    }
    if (isDiscount && lineCents > 0) {
      throw new Error('Een Jumbo-korting heeft een onverwacht positief bedrag.')
    }
    if (isDiscount) discountCents += lineCents
    if (isDeposit) depositCents += lineCents
    calculated += lineCents
    lines.push({
      description: name,
      quantity,
      unitPrice: unitCents / 100,
      lineTotal: lineCents / 100,
      lineType: isDeposit ? 'deposit' : isDiscount ? 'discount' : 'product',
    })
  }
  const grandTotal = moneyCents(parsed.total)
  if (grandTotal === null || grandTotal < 0 || Math.abs(calculated - grandTotal) > 1) {
    throw new Error('Artikelregels, kortingen en statiegeld sluiten niet aan op het Jumbo-bontotaal.')
  }
  return {
    schema_version: '1.0',
    provider: 'jumbo',
    external_receipt_id: transactionId,
    receipt: {
      transactionId,
      purchaseDateTime: detail.purchaseEndOn,
      storeName: String(detail.storeName || 'Jumbo').slice(0, 200),
      grandTotal: grandTotal / 100,
      discountTotal: Math.abs(discountCents) / 100,
      depositTotal: depositCents / 100,
      items: lines,
      paymentMethod: String(parsed.paymentMethod || '').slice(0, 80),
    },
  }
}
