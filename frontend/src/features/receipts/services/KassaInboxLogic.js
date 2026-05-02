import { getKassaCounts, getReceiptStatus } from './KassaStatusService.js'

export function mapReceiptForKassaInbox(receipt) {
  return {
    ...receipt,
    inbox_status: getReceiptStatus(receipt),
  }
}

export function mapReceiptsForKassaInbox(receipts = []) {
  return receipts.map(mapReceiptForKassaInbox)
}

export function buildKassaInboxSummary(receipts = []) {
  return getKassaCounts(receipts)
}
