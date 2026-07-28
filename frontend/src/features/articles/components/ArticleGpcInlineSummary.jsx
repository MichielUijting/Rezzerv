import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { fetchJsonWithAuth, readStoredAuthContext } from '../../../lib/authSession'

function assignmentLabel(assignment) {
  if (!assignment) return 'Nog niet geclassificeerd'
  const code = String(assignment.brick_code || '').trim()
  const description = String(assignment.brick_description || assignment.brick_description_en || '').trim()
  return [code, description].filter(Boolean).join(' — ') || 'Nog niet geclassificeerd'
}

export default function ArticleGpcInlineSummary({ articleId }) {
  const navigate = useNavigate()
  const [target, setTarget] = useState(null)
  const [assignment, setAssignment] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const normalizedArticleId = String(articleId || '').trim()
  const role = String(readStoredAuthContext()?.display_role || '').trim().toLowerCase()
  const canEdit = role === 'admin' || role === 'lid'

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    const findTarget = () => {
      if (cancelled) return
      const section = document.querySelector('[data-testid="article-household-details-section"]')
      const body = section?.querySelector('.rz-article-detail-section-body') || section
      if (body) {
        const host = document.createElement('div')
        host.dataset.testid = 'article-gpc-inline-host'
        host.style.marginTop = '12px'
        body.appendChild(host)
        setTarget(host)
        return
      }
      attempts += 1
      if (attempts < 40) window.setTimeout(findTarget, 100)
    }
    findTarget()
    return () => {
      cancelled = true
      setTarget((current) => {
        current?.remove()
        return null
      })
    }
  }, [normalizedArticleId])

  useEffect(() => {
    let cancelled = false
    if (!normalizedArticleId) {
      setLoading(false)
      return () => { cancelled = true }
    }
    setLoading(true)
    setError('')
    fetchJsonWithAuth(`/api/household-articles/${encodeURIComponent(normalizedArticleId)}/gpc-brick`)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(data?.detail || 'GPC-classificatie kon niet worden geladen.')
        if (!cancelled) setAssignment(data?.assignment || null)
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError?.message || 'GPC-classificatie kon niet worden geladen.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [normalizedArticleId])

  if (!target || !normalizedArticleId) return null

  const content = (
    <div className="rz-field-row" data-testid="article-gpc-inline-summary" style={{ alignItems: 'center' }}>
      <div className="rz-field-row-label">GS1 GPC-classificatie:</div>
      <div className="rz-field-row-value" style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span data-testid="article-gpc-inline-label">
          {loading ? 'Classificatie laden…' : error || assignmentLabel(assignment)}
        </span>
        <button
          type="button"
          className="rz-button"
          data-testid="article-gpc-inline-action"
          onClick={() => navigate(`/voorraad/${encodeURIComponent(normalizedArticleId)}/gpc`)}
          disabled={loading}
        >
          {canEdit ? (assignment ? 'GPC wijzigen' : 'GPC classificeren') : 'GPC bekijken'}
        </button>
      </div>
    </div>
  )

  return createPortal(content, target)
}
