/** Compare only valid GTIN-8/12/13/14 codes, not retailer article numbers.
 * GTIN-13 and GTIN-14 with a leading zero describe the same global identity.
 * Invalid inputs remain distinct; do not silently infer a product from a name.
 */
export function canonicalComparableGtin(value) {
  const digits = String(value ?? '').trim()
  if (!/^(?:\d{8}|\d{12}|\d{13}|\d{14})$/.test(digits)) return ''
  const body = digits.slice(0, -1)
  let total = 0
  for (let position = 0; position < body.length; position += 1) {
    const digit = Number(body[body.length - position - 1])
    total += digit * (position % 2 === 0 ? 3 : 1)
  }
  const expected = (10 - (total % 10)) % 10
  return expected === Number(digits.at(-1)) ? digits.padStart(14, '0') : ''
}

export function equivalentCatalogGtin(left, right) {
  const one = canonicalComparableGtin(left)
  return Boolean(one) && one === canonicalComparableGtin(right)
}

/** For display only: GTIN-14 with one leading zero is the same valid GTIN-13.
 * Keep source evidence and stored identities untouched.
 */
export function displayEd2Gtin(value) {
  const original = String(value ?? '').trim()
  if (!canonicalComparableGtin(original)) return original
  return original.length === 14 && original.startsWith('0')
    ? original.slice(1) : original
}

export function ed2BarcodeIdentityState(item) {
  const catalogBarcode = String(item?.article_code || '').trim()
  const manualBarcode = String(item?.manual_barcode || '').trim()
  const catalogProduct = String(item?.catalog_product_id || '').trim()
  const manualProduct = String(item?.identity_catalog_product_id || '').trim()
  const hasTwoClaims = Boolean(catalogBarcode && manualBarcode)
  const equivalent = hasTwoClaims && equivalentCatalogGtin(catalogBarcode, manualBarcode)
  const differentCatalogOwners = Boolean(
    catalogProduct && manualProduct && catalogProduct !== manualProduct,
  )
  return {
    barcodeConflict: hasTwoClaims && !equivalent && catalogBarcode !== manualBarcode,
    catalogOwnerConflict: Boolean(equivalent && differentCatalogOwners),
    equivalent,
  }
}
