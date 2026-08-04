import { useParams } from 'react-router-dom'
import StoreBatchDetailPage, { StoreBatchDetailContent as BaseStoreBatchDetailContent } from '../stores/StoreBatchDetailPage'
import DayArticleHandlingPanel from './DayArticleHandlingPanel.jsx'

export function StoreBatchDetailContent({ batchIdOverride = '', embedded = false }) {
  const params = useParams()
  const batchId = String(batchIdOverride || params.batchId || '').trim()

  return (
    <div style={{ display: 'grid', gap: 16 }} data-testid="uitpakken-b2-content">
      <BaseStoreBatchDetailContent batchIdOverride={batchIdOverride} embedded={embedded} />
      {batchId ? <DayArticleHandlingPanel batchId={batchId} /> : null}
    </div>
  )
}

export default StoreBatchDetailPage
