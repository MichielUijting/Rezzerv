import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { fetchHouseholdDashboard } from './dashboardApi.js'
import './mobileHome.css'

const METRICS = {
  aankopen: { title: 'Gekochte artikelen', key: 'purchases' },
  uitgaven: { title: 'Uitgaven', key: 'spend' },
  winkels: { title: 'Bezochte winkels', key: 'stores' },
  begroting: { title: 'Begrote uitgaven', key: 'forecast' },
}

function euro(value) {
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
}

function numberLabel(value) {
  const number = Number(value || 0)
  return Number.isInteger(number) ? String(number) : number.toLocaleString('nl-NL', { maximumFractionDigits: 2 })
}

function dateLabel(value) {
  if (!value) return 'Datum onbekend'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat('nl-NL', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date)
}

function MiniBars({ values = [], format = (value) => String(value) }) {
  const max = Math.max(1, ...values.map((item) => Number(item.value || 0)))
  return <div className="rz-dashboard-detail-bars">
    {values.map((item, index) => (
      <div className="rz-dashboard-detail-bar-item" key={item.date || item.week || index}>
        <div className="rz-dashboard-detail-bar-track">
          <span style={{ height: Math.max(5, Math.round((Number(item.value || 0) / max) * 100)) + '%' }} />
        </div>
        <small>{item.date ? String(item.date).slice(5) : 'W' + item.week}</small>
        <strong>{format(item.value)}</strong>
      </div>
    ))}
  </div>
}

function ReceiptList({ receipts = [], showArticleCount = true }) {
  const navigate = useNavigate()
  const [openIds, setOpenIds] = useState(() => new Set())

  function toggle(receiptId) {
    setOpenIds((current) => {
      const next = new Set(current)
      if (next.has(receiptId)) next.delete(receiptId)
      else next.add(receiptId)
      return next
    })
  }

  function openArticle(article) {
    if (article?.household_article_id) {
      navigate('/voorraad/' + encodeURIComponent(article.household_article_id))
      return
    }
    if (article?.global_product_id) {
      navigate('/catalogus/' + encodeURIComponent(article.global_product_id))
    }
  }

  if (!receipts.length) {
    return <p className="rz-dashboard-empty">Geen onderliggende kassabonnen in deze periode.</p>
  }

  return <div className="rz-dashboard-receipts">
    {receipts.map((receipt) => {
      const isOpen = openIds.has(receipt.receipt_id)
      return <article className="rz-dashboard-receipt" key={receipt.receipt_id}>
        <button
          type="button"
          className="rz-dashboard-receipt-summary"
          onClick={() => toggle(receipt.receipt_id)}
          aria-expanded={isOpen}
        >
          <span>
            <strong>{receipt.store || 'Onbekende winkel'}</strong>
            <small>{dateLabel(receipt.purchase_at || receipt.date)}</small>
          </span>
          <span className="rz-dashboard-receipt-totals">
            <strong>{euro(receipt.total)}</strong>
            {showArticleCount ? <small>{numberLabel(receipt.article_count)} artikelen</small> : null}
          </span>
        </button>

        {isOpen ? <div className="rz-dashboard-receipt-detail">
          <div className="rz-dashboard-article-list">
            {(receipt.articles || []).map((article) => {
              const canOpen = Boolean(article.household_article_id || article.global_product_id)
              return <button
                type="button"
                key={article.line_id || article.label}
                className="rz-dashboard-article-row"
                onClick={() => canOpen && openArticle(article)}
                disabled={!canOpen}
              >
                <span>
                  <strong>{article.label}</strong>
                  <small>{numberLabel(article.quantity)}{article.unit ? ' ' + article.unit : ''}</small>
                </span>
                <span>{article.line_total === null || article.line_total === undefined ? '' : euro(article.line_total)}</span>
              </button>
            })}
          </div>
          <button
            type="button"
            className="rz-dashboard-receipt-open"
            onClick={() => navigate('/kassa?receipt=' + encodeURIComponent(receipt.receipt_id))}
          >
            Open kassabon
          </button>
        </div> : null}
      </article>
    })}
  </div>
}

export default function DashboardDetailPage() {
  const { metric = '' } = useParams()
  const definition = METRICS[metric] || METRICS.aankopen
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetchHouseholdDashboard()
      .then((payload) => { if (active) setDashboard(payload) })
      .catch((exc) => { if (active) setError(exc?.message || 'Dashboard kon niet worden geladen.') })
    return () => { active = false }
  }, [])

  const body = useMemo(() => {
    if (!dashboard) return null
    if (definition.key === 'purchases') {
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{numberLabel(dashboard.purchases.current)} artikelen</strong><span>Vorige 7 dagen: {numberLabel(dashboard.purchases.previous)}</span></div>
        <MiniBars values={dashboard.purchases.daily} format={numberLabel} />
        <section className="rz-dashboard-detail-section">
          <h2>Kassabonnen en artikelen</h2>
          <ReceiptList receipts={dashboard.purchases.receipts || []} />
        </section>
      </>
    }
    if (definition.key === 'spend') {
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{euro(dashboard.spend.current)}</strong><span>Vorige 7 dagen: {euro(dashboard.spend.previous)}</span></div>
        <MiniBars values={dashboard.spend.daily} format={euro} />
        <section className="rz-dashboard-detail-section">
          <h2>Kassabonnen</h2>
          <ReceiptList receipts={dashboard.spend.receipts || []} />
        </section>
      </>
    }
    if (definition.key === 'stores') {
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{dashboard.stores.unique} winkels</strong><span>{dashboard.stores.visits} bezoeken</span></div>
        <div className="rz-dashboard-store-list">
          {(dashboard.stores.items || []).map((item) => <details key={item.name}>
            <summary>
              <span><strong>{item.name}</strong><small>{item.visits} bezoek{item.visits === 1 ? '' : 'en'}</small></span>
              <strong>{euro(item.spend)}</strong>
            </summary>
            <ReceiptList receipts={item.receipts || []} />
          </details>)}
        </div>
      </>
    }
    return <>
      <div className="rz-dashboard-detail-summary"><strong>{euro(dashboard.forecast.total)}</strong><span>Komende 4 weken</span></div>
      <MiniBars values={dashboard.forecast.weeks} format={euro} />
      <p className="rz-dashboard-method">{dashboard.forecast.method}</p>
      <section className="rz-dashboard-detail-section">
        <h2>Basis van de begroting</h2>
        <p className="rz-dashboard-method">De onderstaande kassabonnen uit de afgelopen 8 weken vormen de huidige basis voor de prognose.</p>
        <ReceiptList receipts={dashboard.forecast.basis_receipts || []} />
      </section>
    </>
  }, [dashboard, definition.key])

  return <main className="rz-mobile-home" data-testid={'dashboard-detail-' + metric}>
    <MobileModuleHeader title={definition.title} testId="dashboard-detail-header" />
    <section className="rz-mobile-home-inner">
      {error ? <div role="alert" className="rz-dashboard-error">{error}</div> : null}
      {!dashboard && !error ? <p role="status">Dashboard laden…</p> : body}
    </section>
  </main>
}
