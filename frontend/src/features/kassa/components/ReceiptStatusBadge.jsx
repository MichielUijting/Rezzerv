function normalizeReceiptStatusLabel(value) {
  const normalized = String(value || '').trim()
  if (!normalized || normalized === 'Handmatig' || normalized.toLowerCase() === 'manual') return 'Controle nodig'
  return normalized
}

function inboxStatusStyle(value) {
  const normalizedValue = normalizeReceiptStatusLabel(value)
  if (normalizedValue === 'Gecontroleerd') {
    return {
      background: '#ECFDF3',
      color: '#027A48',
      border: '1px solid #ABEFC6',
    }
  }
  if (normalizedValue === 'Controle nodig') {
    return {
      background: '#FFFAEB',
      color: '#166534',
      border: '1px solid #FEDF89',
    }
  }
  return {
    background: '#FFFAEB',
    color: '#166534',
    border: '1px solid #FEDF89',
  }
}

export default function ReceiptStatusBadge({ value }) {
  const normalizedValue = normalizeReceiptStatusLabel(value)
  return (
    <span
      data-testid={`receipt-inbox-status-${String(normalizedValue || '').toLowerCase().replace(/\s+/g, '-')}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '13px',
        fontWeight: 700,
        whiteSpace: 'nowrap',
        ...inboxStatusStyle(normalizedValue),
      }}
    >
      {normalizedValue || '-'}
    </span>
  )
}
