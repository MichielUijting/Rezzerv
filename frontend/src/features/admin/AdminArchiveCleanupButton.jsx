import React, { useState } from 'react'
import Button from '../../ui/Button'

function getAuthHeaders() {
  const token = localStorage.getItem('rezzerv_token') || ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default function AdminArchiveCleanupButton() {
  const [message, setMessage] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  async function handlePurgeArchivedReceipts() {
    const confirmed = window.confirm('Gearchiveerde kassabondata opruimen? Actieve kassabonnen blijven behouden.')
    if (!confirmed) return

    setIsBusy(true)
    setMessage('Archief wordt opgeruimd…')
    try {
      const response = await fetch('/api/dev/receipts/purge-archived', {
        method: 'POST',
        headers: getAuthHeaders(),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || 'Gearchiveerde kassabondata kon niet worden opgeruimd.')
      }
      const deleted = data.deleted || {}
      const after = data.after || {}
      setMessage(`Archief opgeschoond: ${deleted.receipt_tables || 0} kassabon(nen), ${deleted.raw_receipts || 0} bronbestand(en), ${deleted.receipt_table_lines || 0} regel(s). Actieve kassabonnen over: ${after.active_receipt_tables ?? 'onbekend'}.`)
    } catch (error) {
      setMessage(error?.message || 'Gearchiveerde kassabondata kon niet worden opgeruimd.')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div
      data-testid="admin-archive-cleanup-panel"
      style={{
        position: 'fixed',
        right: '24px',
        top: '148px',
        width: '320px',
        zIndex: 20,
        background: 'var(--rz-card-bg, #fff)',
        border: '1px solid var(--rz-border, #d7e0d7)',
        borderRadius: '12px',
        boxShadow: '0 12px 24px rgba(0,0,0,0.14)',
        padding: '12px',
      }}
    >
      <h3 style={{ margin: '0 0 6px 0' }}>Archiefbeheer</h3>
      <p className="rz-admin-muted" style={{ marginTop: 0 }}>
        Ruimt alleen kassabondata op die al gearchiveerd is. Actieve bonnen blijven behouden.
      </p>
      <Button
        variant="secondary"
        onClick={handlePurgeArchivedReceipts}
        disabled={isBusy}
        data-testid="admin-purge-archived-receipts-button"
      >
        {isBusy ? 'Archief opruimen…' : 'Verwijder gearchiveerde kassabonnen'}
      </Button>
      {message ? (
        <div className="rz-admin-message" data-testid="admin-purge-archived-receipts-message" style={{ marginTop: '8px' }}>
          {message}
        </div>
      ) : null}
    </div>
  )
}
