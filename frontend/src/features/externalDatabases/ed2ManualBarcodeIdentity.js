// The manually registered barcode is evidence, not a confirmed Catalogus identity.
const ascii = (value) => String(value ?? '').normalize('NFKD')
  .replace(/[\u0300-\u036f]/g, '').replace(/[^\x00-\x7F]/g, '')
const normalizeRetailer = (value) => ascii(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
const normalizeReceipt = (value) => ascii(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ')
const normalizeCode = (value) => String(value ?? '').trim().toLowerCase().replace(/\s+/g, '')
export function manualBarcodeKey(retailer, receiptText, articleCode) {
  return JSON.stringify([normalizeRetailer(retailer), normalizeReceipt(receiptText), normalizeCode(articleCode)])
}
