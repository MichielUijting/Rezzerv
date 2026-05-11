import { useEffect, useState } from 'react'
import ScreenCard from '../../../ui/ScreenCard'
import Button from '../../../ui/Button'
import { normalizeErrorMessage } from '../../stores/storeImportShared'

export default function ReceiptPreviewCard({
  receipt,
  transientPreview = null,
  isCollapsed,
  onToggleCollapse,
  loadReceiptPreview,
}) {
  const [selectedVariant, setSelectedVariant] = useState('original')
  const [previewState, setPreviewState] = useState({
    status: 'idle',
    blobUrl: '',
    contentType: '',
    isPdf: false,
    isImage: false,
    isHtml: false,
    isText: false,
    textContent: '',
    error: '',
  })
  const hasTransientPreview = Boolean(transientPreview?.originalUrl)
  const supportsProcessedPreview = hasTransientPreview || (receipt?.mime_type ? String(receipt.mime_type).toLowerCase().startsWith('image/') : false)
  const previewTitle = selectedVariant === 'processed' ? 'Bewerkte kassabon' : 'Originele kassabon'

  useEffect(() => {
    setSelectedVariant('original')
  }, [receipt?.id, transientPreview?.originalUrl, transientPreview?.processedUrl])

  useEffect(() => {
    let cancelled = false
    let activeUrl = ''

    async function loadPreview() {
      if (hasTransientPreview) {
        const transientUrl = selectedVariant === 'processed' ? transientPreview?.processedUrl : transientPreview?.originalUrl
        if (!transientUrl) {
          setPreviewState({ status: 'error', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: 'Bewerkte bonpreview is nog niet beschikbaar.' })
          return
        }
        setPreviewState({ status: 'ready', blobUrl: transientUrl, contentType: 'image/png', isPdf: false, isImage: true, isHtml: false, isText: false, textContent: '', error: '' })
        return
      }
      if (!receipt?.id) {
        setPreviewState({ status: 'idle', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
        return
      }
      setPreviewState({ status: 'loading', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: '' })
      try {
        if (typeof loadReceiptPreview !== 'function') throw new Error('Preview-loader ontbreekt.')
        const result = await loadReceiptPreview(receipt.id, selectedVariant === 'processed' ? 'processed' : 'original')
        if (cancelled) {
          if (result.blobUrl) window.URL.revokeObjectURL(result.blobUrl)
          return
        }
        activeUrl = result.blobUrl
        setPreviewState({ status: 'ready', error: '', ...result })
      } catch (err) {
        if (!cancelled) {
          setPreviewState({ status: 'error', blobUrl: '', contentType: '', isPdf: false, isImage: false, isHtml: false, isText: false, textContent: '', error: normalizeErrorMessage(err?.message) || 'Preview laden mislukt.' })
        }
      }
    }

    loadPreview()
    return () => {
      cancelled = true
      if (!hasTransientPreview && activeUrl) window.URL.revokeObjectURL(activeUrl)
    }
  }, [receipt?.id, receipt?.mime_type, selectedVariant, transientPreview?.originalUrl, transientPreview?.processedUrl, hasTransientPreview, loadReceiptPreview])

  return (
    <ScreenCard>
      {isCollapsed ? (
        <div
          style={{
            display: 'grid',
            alignContent: 'start',
            justifyItems: 'center',
            minHeight: '100%',
          }}
          data-testid="receipt-preview-card"
        >
          <button
            type="button"
            onClick={onToggleCollapse}
            data-testid="receipt-preview-toggle"
            aria-label="Kassabon uitklappen"
            title="Uitklappen"
            className="rz-expand-chip"
            style={{ width: '32px', height: '32px' }}
          >
            +
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '16px' }} data-testid="receipt-preview-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'grid', gap: '8px' }}>
              <div style={{ fontWeight: 700, fontSize: '22px' }}>{previewTitle}</div>
              <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start', gap: '8px' }}>
                <Button type="button" variant={selectedVariant === 'original' ? 'primary' : 'secondary'} onClick={() => setSelectedVariant('original')} style={{ padding: '8px 14px', minWidth: '110px' }}>Origineel</Button>
                <Button type="button" variant={selectedVariant === 'processed' ? 'primary' : 'secondary'} onClick={() => setSelectedVariant('processed')} disabled={!supportsProcessedPreview} style={{ padding: '8px 14px', minWidth: '110px' }}>Bewerkt</Button>
              </div>
            </div>
            <div className="rz-stock-table-actions" style={{ justifyContent: 'flex-start' }}>
              <button
                type="button"
                onClick={onToggleCollapse}
                data-testid="receipt-preview-toggle"
                aria-label="Kassabon inklappen"
                title="Inklappen"
                className="rz-expand-chip"
                style={{ width: '32px', height: '32px' }}
              >
                −
              </button>
            </div>
          </div>

          <div
            style={{
              border: '1px solid #d0d5dd',
              borderRadius: '8px',
              minHeight: '420px',
              background: '#f8fafc',
              overflow: 'auto',
              display: 'block',
              padding: previewState.isImage ? '16px' : '0',
              height: '72vh',
              maxHeight: '72vh',
            }}
          >
            {previewState.status === 'loading' ? (
              <div style={{ color: '#475467', fontWeight: 600, padding: '16px' }}>Preview laden…</div>
            ) : null}

            {previewState.status === 'error' ? (
              <div className="rz-inline-feedback rz-inline-feedback--warning" data-testid="receipt-preview-fallback" style={{ maxWidth: '560px', margin: '16px' }}>
                {previewState.error}
              </div>
            ) : null}

            {previewState.status === 'ready' && previewState.isPdf ? (
              <iframe
                title={previewTitle}
                src={previewState.blobUrl}
                style={{ width: '100%', height: '100%', minHeight: '70vh', border: 0 }}
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isImage ? (
              <img
                src={previewState.blobUrl}
                alt={previewTitle}
                style={{ maxWidth: '100%', height: 'auto', display: 'block', margin: '0 auto' }}
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isHtml ? (
              <iframe
                title={previewTitle}
                srcDoc={previewState.textContent}
                style={{ width: '100%', height: '100%', minHeight: '70vh', border: 0, background: '#ffffff' }}
              />
            ) : null}

            {previewState.status === 'ready' && previewState.isText ? (
              <pre style={{ margin: 0, padding: '16px', whiteSpace: 'pre-wrap', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace', fontSize: '13px' }}>
                {previewState.textContent}
              </pre>
            ) : null}

            {previewState.status === 'ready' && !previewState.isPdf && !previewState.isImage && !previewState.isHtml && !previewState.isText ? (
              <div className="rz-inline-feedback rz-inline-feedback--warning" style={{ margin: '16px' }}>
                Previewtype wordt niet ondersteund.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </ScreenCard>
  )
}
