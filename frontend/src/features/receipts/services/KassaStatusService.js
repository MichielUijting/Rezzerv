export function getReceiptStatus(receipt) {
  return receipt?.po_norm_status_label || ''
}

export function getKassaCounts(receipts = []) {
  return {
    Handmatig: 0,
    'Controle nodig': receipts.filter(r => r?.po_norm_status_label === 'Controle nodig').length,
    Gecontroleerd: receipts.filter(r => r?.po_norm_status_label === 'Gecontroleerd').length,
  }
}
