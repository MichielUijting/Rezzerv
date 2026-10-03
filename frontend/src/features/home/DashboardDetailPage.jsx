import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { fetchHouseholdDashboard, fetchHouseholdDashboardDrilldown } from './dashboardApi.js'
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

function groupReceiptsByDate(receipts = []) {
  const groups = new Map()
  for (const receipt of receipts) {
    const key = String(receipt.date || receipt.purchase_at || '').slice(0, 10) || 'onbekend'
    const group = groups.get(key) || { key, label: dateLabel(receipt.purchase_at || receipt.date), total: 0, articleCount: 0, receipts: [] }
    group.total += Number(receipt.total || 0)
    group.articleCount += Number(receipt.article_count || 0)
    group.receipts.push(receipt)
    groups.set(key, group)
  }
  return Array.from(groups.values()).sort((a, b) => String(b.key).localeCompare(String(a.key)))
}

function groupReceiptsByStore(receipts = []) {
  const groups = new Map()
  for (const receipt of receipts) {
    const key = String(receipt.store || 'Onbekende winkel').trim().toLowerCase()
    const group = groups.get(key) || { key, label: receipt.store || 'Onbekende winkel', total: 0, articleCount: 0, receipts: [] }
    group.total += Number(receipt.total || 0)
    group.articleCount += Number(receipt.article_count || 0)
    group.receipts.push(receipt)
    groups.set(key, group)
  }
  return Array.from(groups.values()).sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'nl'))
}

function aggregateCategories(receipts = []) {
  const groups = new Map()
  for (const receipt of receipts) {
    for (const group of receipt.group_allocations || []) {
      const key = String(group.key || 'unclassified')
      const current = groups.get(key) || {
        key,
        label: group.label || 'Niet ingedeeld',
        total: 0,
      }
      current.total += Number(group.value || 0)
      groups.set(key, current)
    }
  }

  const unclassified = groups.get('unclassified') || null
  const ranked = Array.from(groups.values())
    .filter((item) => item.key !== 'unclassified')
    .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'nl'))
  const visible = ranked.slice(0, 5)
  const rest = ranked.slice(5)
  if (rest.length) {
    visible.push({
      key: 'other',
      label: 'Overig',
      total: rest.reduce((sum, item) => sum + Number(item.total || 0), 0),
    })
  }
  if (unclassified) visible.push(unclassified)
  return visible
}

function aggregateArticles(receipts = []) {
  const articles = new Map()
  for (const receipt of receipts) {
    for (const article of receipt.articles || []) {
      const key = String(article.household_article_id || article.global_product_id || article.label || '').trim().toLowerCase()
      if (!key) continue
      const current = articles.get(key) || {
        key,
        label: article.label || 'Artikel',
        quantity: 0,
        total: 0,
        household_article_id: article.household_article_id || null,
        global_product_id: article.global_product_id || null,
      }
      current.quantity += Number(article.quantity || 0)
      current.total += Number(article.line_total || 0)
      if (!current.household_article_id && article.household_article_id) current.household_article_id = article.household_article_id
      if (!current.global_product_id && article.global_product_id) current.global_product_id = article.global_product_id
      articles.set(key, current)
    }
  }
  return Array.from(articles.values()).sort((a, b) => b.quantity - a.quantity || a.label.localeCompare(b.label, 'nl'))
}

function openArticleRoute(navigate, article) {
  if (article?.household_article_id) {
    navigate('/voorraad/' + encodeURIComponent(article.household_article_id))
    return true
  }
  if (article?.global_product_id) {
    navigate('/catalogus/' + encodeURIComponent(article.global_product_id))
    return true
  }
  return false
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

function familyViewFromReceipts(receipts = [], label = '', series = 'current') {
  const rows = aggregateCategories(receipts)
  const segments = rows.map((group) => ({
    key: group.key,
    label: group.label,
    value: Number(group.total || 0),
  }))
  const total = segments.reduce((sum, item) => sum + Number(item.value || 0), 0)
  const point = {
    label,
    current: 0,
    previous: 0,
    current_segments: [],
    previous_segments: [],
  }
  point[series] = total
  point[series + '_segments'] = segments
  return {
    points: [point],
    legend: rows.map((group) => ({ key: group.key, label: group.label })),
  }
}

function StackedFamilyBars({ view = null, currency = true }) {
  const points = view?.points || []
  const legend = view?.legend || []
  const classByKey = new Map(legend.map((item, index) => [item.key, index % 7]))
  const max = Math.max(1, ...points.flatMap((point) => [Number(point.current || 0), Number(point.previous || 0)]))
  const middle = max / 2

  function renderStack(point, series) {
    const total = Number(point?.[series] || 0)
    const segments = point?.[series + '_segments'] || []
    return <span
      className={'rz-dashboard-bar rz-dashboard-stacked-bar rz-dashboard-stacked-bar--' + series}
      style={{ height: Math.max(3, Math.round((total / max) * 100)) + '%' }}
      aria-label={`${point.label}, ${series === 'current' ? 'huidige' : 'vergelijkings'} periode: ${currency ? euro(total) : numberLabel(total)}`}
    >
      {segments.map((segment) => (
        <span
          key={segment.key}
          className={'rz-dashboard-stack-segment rz-dashboard-stack-segment--' + (classByKey.get(segment.key) ?? 0)}
          style={{ flexGrow: Math.max(0.0001, Number(segment.value || 0)) }}
          title={`${segment.label}: ${currency ? euro(segment.value) : numberLabel(segment.value)}`}
        />
      ))}
    </span>
  }

  if (!points.length) return null

  return <div className="rz-dashboard-detail-family-chart">
    <div className="rz-dashboard-comparison-chart rz-dashboard-stacked-chart" aria-label="Gestapelde grafiek per productfamilie">
      <div className="rz-dashboard-y-axis" aria-hidden="true">
        <span>{currency ? euro(max) : numberLabel(max)}</span>
        <span>{currency ? euro(middle) : numberLabel(middle)}</span>
        <span>{currency ? euro(0) : '0'}</span>
      </div>
      <div className="rz-dashboard-chart-plot">
        <div className="rz-dashboard-gridline rz-dashboard-gridline--top" />
        <div className="rz-dashboard-gridline rz-dashboard-gridline--mid" />
        <div className="rz-dashboard-gridline rz-dashboard-gridline--base" />
        <div className="rz-dashboard-comparison-bars">
          {points.map((point, index) => (
            <div className="rz-dashboard-comparison-group" key={point.label || index}>
              <div className="rz-dashboard-comparison-pair">
                {renderStack(point, 'previous')}
                {renderStack(point, 'current')}
              </div>
              <small>{point.label}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
    {legend.length ? <div className="rz-dashboard-stack-legend" aria-label="Productfamilies">
      {legend.map((item, index) => (
        <span key={item.key}>
          <i className={'rz-dashboard-stack-key rz-dashboard-stack-segment--' + (index % 7)} />
          {item.label}
        </span>
      ))}
    </div> : null}
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
    openArticleRoute(navigate, article)
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
            onClick={() => navigate('/kassa?view=bonnen&receipt=' + encodeURIComponent(receipt.receipt_id))}
          >
            Open kassabon
          </button>
        </div> : null}
      </article>
    })}
  </div>
}

function ReceiptGroupList({ groups = [], metric = 'spend' }) {
  if (!groups.length) {
    return <p className="rz-dashboard-empty">Geen onderliggende gegevens in deze periode.</p>
  }
  return <div className="rz-dashboard-group-list">
    {groups.map((group) => <details className="rz-dashboard-group" key={group.key}>
      <summary>
        <span>
          <strong>{group.label}</strong>
          <small>{group.receipts.length} kassabon{group.receipts.length === 1 ? '' : 'nen'}</small>
        </span>
        <span>
          <strong>{metric === 'purchases' ? numberLabel(group.articleCount) + ' artikelen' : euro(group.total)}</strong>
          {metric === 'purchases' ? <small>{euro(group.total)}</small> : <small>{numberLabel(group.articleCount)} artikelen</small>}
        </span>
      </summary>
      <ReceiptList receipts={group.receipts} />
    </details>)}
  </div>
}

function CategoryTotals({ receipts = [] }) {
  const rows = useMemo(() => aggregateCategories(receipts), [receipts])
  const total = rows.reduce((sum, item) => sum + Number(item.total || 0), 0)
  if (!rows.length) {
    return <p className="rz-dashboard-empty">Nog geen categorie-indeling beschikbaar voor deze periode.</p>
  }
  return <div className="rz-dashboard-category-totals">
    <div className="rz-dashboard-category-stack" aria-label="Uitgaven per productfamilie">
      {rows.map((group, index) => (
        <span
          key={group.key}
          className={'rz-dashboard-category-stack-segment rz-dashboard-stack-segment--' + (index % 7)}
          style={{ flexGrow: Math.max(0.0001, Number(group.total || 0)) }}
          title={`${group.label}: ${euro(group.total)}`}
        />
      ))}
    </div>
    {rows.map((group, index) => (
      <div className="rz-dashboard-category-total-row" key={group.key}>
        <span>
          <i className={'rz-dashboard-stack-key rz-dashboard-stack-segment--' + (index % 7)} />
          <strong>{group.label}</strong>
        </span>
        <strong>{euro(group.total)}{total > 0 ? ' · ' + Math.round((Number(group.total || 0) / total) * 100) + '%' : ''}</strong>
      </div>
    ))}
  </div>
}

function ArticleTotals({ receipts = [] }) {
  const navigate = useNavigate()
  const rows = useMemo(() => aggregateArticles(receipts), [receipts])
  if (!rows.length) {
    return <p className="rz-dashboard-empty">Geen artikelen gevonden in deze periode.</p>
  }
  return <div className="rz-dashboard-article-totals">
    {rows.map((article) => {
      const canOpen = Boolean(article.household_article_id || article.global_product_id)
      return <button
        type="button"
        key={article.key}
        className="rz-dashboard-article-total-row"
        disabled={!canOpen}
        onClick={() => openArticleRoute(navigate, article)}
      >
        <span>
          <strong>{article.label}</strong>
          <small>{numberLabel(article.quantity)} gekocht</small>
        </span>
        <span>{euro(article.total)}</span>
      </button>
    })}
  </div>
}

function RepeatPurchaseList({ items = [] }) {
  const navigate = useNavigate()
  if (!items.length) {
    return <p className="rz-dashboard-empty">Nog onvoldoende herhalingskoop gevonden om aankopen te begroten.</p>
  }
  return <div className="rz-dashboard-repeat-list">
    {items.map((item, index) => {
      const canOpen = Boolean(item.household_article_id || item.global_product_id)
      return <button
        type="button"
        className="rz-dashboard-repeat-row"
        key={item.identity + '-' + item.expected_date + '-' + index}
        disabled={!canOpen}
        onClick={() => openArticleRoute(navigate, item)}
      >
        <span>
          <strong>{item.label}</strong>
          <small>Verwacht {dateLabel(item.expected_date)} · ritme circa {item.cadence_days} dagen</small>
        </span>
        <span>
          <strong>{euro(item.expected_amount)}</strong>
          <small>{numberLabel(item.expected_quantity)} verwacht</small>
        </span>
      </button>
    })}
  </div>
}

export default function DashboardDetailPage() {
  const { metric = '' } = useParams()
  const [searchParams] = useSearchParams()
  const definition = METRICS[metric] || METRICS.aankopen
  const [dashboard, setDashboard] = useState(null)
  const [barDrilldown, setBarDrilldown] = useState(null)
  const [error, setError] = useState('')
  const granularity = searchParams.get('granularity') || ''
  const bucketIndex = Number(searchParams.get('bucket'))
  const series = searchParams.get('series') || 'current'
  const comparison = searchParams.get('comparison') || 'previous'
  const groupKey = searchParams.get('group') || ''
  const hasBarDrilldown = ['days', 'weeks', 'months'].includes(granularity)
    && Number.isInteger(bucketIndex)
    && bucketIndex >= 0
    && bucketIndex <= 3

  useEffect(() => {
    let active = true
    setError('')
    if (hasBarDrilldown) {
      fetchHouseholdDashboardDrilldown({
        metric: definition.key,
        granularity,
        bucketIndex,
        series,
        comparison,
        groupKey,
      })
        .then((payload) => {
          if (!active) return
          setBarDrilldown(payload)
          setDashboard(null)
        })
        .catch((exc) => { if (active) setError(exc?.message || 'Dashboarddetail kon niet worden geladen.') })
    } else {
      fetchHouseholdDashboard()
        .then((payload) => {
          if (!active) return
          setDashboard(payload)
          setBarDrilldown(null)
        })
        .catch((exc) => { if (active) setError(exc?.message || 'Dashboard kon niet worden geladen.') })
    }
    return () => { active = false }
  }, [hasBarDrilldown, definition.key, granularity, bucketIndex, series, comparison, groupKey])

  const body = useMemo(() => {
    if (barDrilldown) {
      const receipts = barDrilldown.receipts || []
      if (definition.key === 'forecast') {
        return <>
          <div className="rz-dashboard-detail-summary">
            <strong>{euro(barDrilldown.forecast_total)}</strong>
            <span>{barDrilldown.label}</span>
          </div>
          <section className="rz-dashboard-detail-section">
            <h2>Verwachte herhalingskopen</h2>
            <RepeatPurchaseList items={barDrilldown.forecast_items || []} />
          </section>
        </>
      }
      if (definition.key === 'stores') {
        return <>
          <div className="rz-dashboard-detail-summary">
            <strong>{numberLabel((barDrilldown.stores || []).length)} winkels</strong>
            <span>{barDrilldown.label}</span>
          </div>
          <div className="rz-dashboard-store-list">
            {(barDrilldown.stores || []).map((item) => <details key={item.name}>
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
        <div className="rz-dashboard-detail-summary">
          <strong>{euro(barDrilldown.spend)}</strong>
          <span>{barDrilldown.label}{barDrilldown.group_label ? ' · ' + barDrilldown.group_label : ''} · {series === 'previous' ? 'vergelijkingsperiode' : 'huidige periode'}</span>
        </div>
        <StackedFamilyBars
          view={familyViewFromReceipts(receipts, barDrilldown.label, series)}
          currency
        />
        <section className="rz-dashboard-detail-section">
          <h2>{barDrilldown.group_label ? 'Artikelen in ' + barDrilldown.group_label : 'Artikelen in deze staaf'}</h2>
          <ArticleTotals receipts={receipts} />
        </section>
        {!barDrilldown.group_label ? <section className="rz-dashboard-detail-section">
          <h2>Per productfamilie</h2>
          <CategoryTotals receipts={receipts} />
        </section> : null}
        <section className="rz-dashboard-detail-section">
          <h2>Per winkel</h2>
          <ReceiptGroupList groups={groupReceiptsByStore(receipts)} metric="spend" />
        </section>
        <section className="rz-dashboard-detail-section">
          <h2>Kassabonnen in deze staaf</h2>
          <ReceiptList receipts={receipts} />
        </section>
      </>
    }
    if (!dashboard) return null
    if (definition.key === 'purchases') {
      const receipts = dashboard.purchases.receipts || []
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{numberLabel(dashboard.purchases.current)} artikelen</strong><span>Vorige 7 dagen: {numberLabel(dashboard.purchases.previous)}</span></div>
        <MiniBars values={dashboard.purchases.daily} format={numberLabel} />
        <section className="rz-dashboard-detail-section">
          <h2>Per dag</h2>
          <ReceiptGroupList groups={groupReceiptsByDate(receipts)} metric="purchases" />
        </section>
        <section className="rz-dashboard-detail-section">
          <h2>Artikelen in deze periode</h2>
          <ArticleTotals receipts={receipts} />
        </section>
      </>
    }
    if (definition.key === 'spend') {
      const receipts = dashboard.spend.receipts || []
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{euro(dashboard.spend.current)}</strong><span>Vorige 7 dagen: {euro(dashboard.spend.previous)}</span></div>
        <StackedFamilyBars view={dashboard.spend.group_views?.days} currency />
        <section className="rz-dashboard-detail-section">
          <h2>Per productfamilie</h2>
          <CategoryTotals receipts={receipts} />
        </section>
        <section className="rz-dashboard-detail-section">
          <h2>Per winkel</h2>
          <ReceiptGroupList groups={groupReceiptsByStore(receipts)} metric="spend" />
        </section>
        <section className="rz-dashboard-detail-section">
          <h2>Per dag</h2>
          <ReceiptGroupList groups={groupReceiptsByDate(receipts)} metric="spend" />
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
        <h2>Verwachte herhalingskopen</h2>
        <p className="rz-dashboard-method">Alleen artikelen met voldoende koopgeschiedenis worden meegenomen. Het verwachte koopmoment volgt het historische koopritme per artikel.</p>
        <RepeatPurchaseList items={dashboard.forecast.items || []} />
      </section>
      <section className="rz-dashboard-detail-section">
        <h2>Historische basis</h2>
        <ReceiptList receipts={dashboard.forecast.basis_receipts || []} />
      </section>
    </>
  }, [dashboard, barDrilldown, definition.key, series])

  const detailTitle = barDrilldown
    ? `${definition.title} · ${barDrilldown.label}${barDrilldown.group_label ? ' · ' + barDrilldown.group_label : ''}`
    : definition.title

  return <main className="rz-mobile-home" data-testid={'dashboard-detail-' + metric}>
    <MobileModuleHeader title={detailTitle} testId="dashboard-detail-header" />
    <section className="rz-mobile-home-inner">
      {error ? <div role="alert" className="rz-dashboard-error">{error}</div> : null}
      {!dashboard && !barDrilldown && !error ? <p role="status">Dashboard inlezen.</p> : body}
    </section>
  </main>
}
