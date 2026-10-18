// One visual status mapping for the mobile receipt lists in Kassa and Uitpakken.
// Presentation only: the authoritative processing status is never changed here.
export function mobileReceiptStatusClass(status) {
  const normalized = String(status || '').trim().toLocaleLowerCase('nl-NL')
  if (normalized === 'controle nodig') return 'rz-mobile-unpack-card--needs-review'
  if (normalized === 'gecontroleerd') return 'rz-mobile-unpack-card--checked'
  return ''
}
