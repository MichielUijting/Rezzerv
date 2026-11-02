/** Show the confirmed GS1 type in overviews without exposing the full hierarchy. */
export function gs1ProductTypeLabel(product) {
  const name = String(product?.gpc_brick_name || '').trim()
  if (name) return name
  return String(product?.gpc_brick_code || '').trim()
    ? 'Omschrijving ontbreekt' : 'Niet geclassificeerd'
}
