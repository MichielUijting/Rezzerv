function requirePoNormStatusLabel(value) {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return 'API-contractfout: po_norm_status_label ontbreekt'
  }
  return normalized
}

function inboxStatusStyle(value) {
  if (value === 'Gecontroleerd') {
    return {
      background: '#ECFDF3',
      color: '#027A48',
      border: '1px solid #ABEFC6',
    }
  }
  if (value === 'Controle nodig') {
    return {
      background: '#FFFAEB',
      color: '#166534',
      border: '1px solid #FEDF89',
    }
  }
  return {
    background: '#FEF3F2',
    color: '#B42318',
    border: '1px solid #FECDCA',
  }
}

export default function ReceiptStatusBadge({ value }) {
  const label = requirePoNormStatusLabel(value)
  return (
    <span
      data-testid={`receipt-inbox-status-${String(label || '').toLowerCase().replace(/\s+/g, '-')}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4px 10px',
        borderRadius: '999px',
        fontSize: '13px',
        fontWeight: 700,
        whiteSpace: 'nowrap',
        ...inboxStatusStyle(label),
      }}
    >
      {label}
    </span>
  )
}
