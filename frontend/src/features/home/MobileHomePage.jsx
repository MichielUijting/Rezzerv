import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { fetchAlmostOutCount, fetchHouseholdDashboard, fetchRetailerPendingReceiptSummary } from './dashboardApi.js'
import { readDashboardCardOrder, writeDashboardCardOrder } from './dashboardCardOrder.js'
import './mobileHome.css'

const PERIODS = [
  { key: 'days', label: 'Dagen', currentLabel: 'laatste 4 dagen', previousLabel: '4 dagen daarvoor' },
  { key: 'weeks', label: 'Weken', currentLabel: 'laatste 4 weken', previousLabel: '4 weken daarvoor' },
  { key: 'months', label: 'Maanden', currentLabel: 'laatste 4 maanden', previousLabel: '4 maanden daarvoor' },
]

function firstName(context) {
  const explicit = String(context?.first_name || '').trim()
  if (explicit) return explicit
  const candidate = String(context?.email || '').split('@')[0].trim().split(/[._-]+/)[0]
  if (!candidate) return ''
  return candidate.charAt(0).toUpperCase() + candidate.slice(1)
}

function euro(value) {
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
}

function numberLabel(value) {
  const number = Number(value || 0)
  return Number.isInteger(number)
    ? String(number)
    : number.toLocaleString('nl-NL', { maximumFractionDigits: 1 })
}

function compactAxis(value, currency = false) {
  const number = Number(value || 0)
  if (currency) {
    if (Math.abs(number) >= 1000) return '€' + (number / 1000).toLocaleString('nl-NL', { maximumFractionDigits: 1 }) + 'k'
    return '€' + Math.round(number)
  }
  if (Math.abs(number) >= 1000) return (number / 1000).toLocaleString('nl-NL', { maximumFractionDigits: 1 }) + 'k'
  return numberLabel(number)
}

function sumSeries(points = [], key = 'current') {
  return points.reduce((total, point) => total + Number(point?.[key] || 0), 0)
}

function deltaText(current, previous, formatter, period) {
  const diff = Number(current || 0) - Number(previous || 0)
  if (Math.abs(diff) < 0.0001) return 'gelijk aan ' + period.previousLabel
  return (diff > 0 ? '+' : '−') + formatter(Math.abs(diff)) + ' t.o.v. ' + period.previousLabel
}

function ComparisonChart({ points = [], currency = false, onBarActivate = null }) {
  const max = Math.max(1, ...points.flatMap((point) => [Number(point.current || 0), Number(point.previous || 0)]))
  const middle = max / 2
  return <div className="rz-dashboard-comparison-chart" aria-label="Vergelijkingsgrafiek">
    <div className="rz-dashboard-y-axis" aria-hidden="true">
      <span>{compactAxis(max, currency)}</span>
      <span>{compactAxis(middle, currency)}</span>
      <span>{compactAxis(0, currency)}</span>
    </div>
    <div className="rz-dashboard-chart-plot">
      <div className="rz-dashboard-gridline rz-dashboard-gridline--top" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--mid" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--base" />
      <div className="rz-dashboard-comparison-bars">
        {points.map((point, index) => (
          <div className="rz-dashboard-comparison-group" key={point.label || index}>
            <div className="rz-dashboard-comparison-pair">
              <span
                className="rz-dashboard-bar rz-dashboard-bar--previous"
                role={onBarActivate ? 'button' : undefined}
                tabIndex={onBarActivate ? 0 : undefined}
                title={'Vorige periode: ' + (currency ? euro(point.previous) : numberLabel(point.previous))}
                aria-label={onBarActivate ? `${point.label}, vergelijkingsperiode: ${currency ? euro(point.previous) : numberLabel(point.previous)}` : undefined}
                onPointerDown={onBarActivate ? (event) => event.stopPropagation() : undefined}
                onClick={onBarActivate ? (event) => { event.stopPropagation(); onBarActivate(index, 'previous', point) } : undefined}
                onKeyDown={onBarActivate ? (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    event.stopPropagation()
                    onBarActivate(index, 'previous', point)
                  }
                } : undefined}
                style={{ height: Math.max(3, Math.round((Number(point.previous || 0) / max) * 100)) + '%' }}
              />
              <span
                className="rz-dashboard-bar rz-dashboard-bar--current"
                role={onBarActivate ? 'button' : undefined}
                tabIndex={onBarActivate ? 0 : undefined}
                title={'Huidige periode: ' + (currency ? euro(point.current) : numberLabel(point.current))}
                aria-label={onBarActivate ? `${point.label}, huidige periode: ${currency ? euro(point.current) : numberLabel(point.current)}` : undefined}
                onPointerDown={onBarActivate ? (event) => event.stopPropagation() : undefined}
                onClick={onBarActivate ? (event) => { event.stopPropagation(); onBarActivate(index, 'current', point) } : undefined}
                onKeyDown={onBarActivate ? (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    event.stopPropagation()
                    onBarActivate(index, 'current', point)
                  }
                } : undefined}
                style={{ height: Math.max(3, Math.round((Number(point.current || 0) / max) * 100)) + '%' }}
              />
            </div>
            <small>{point.label}</small>
          </div>
        ))}
      </div>
    </div>
  </div>
}

function StackedComparisonChart({ view = null, currency = false, onSegmentActivate = null, paletteLegend = [] }) {
  const points = view?.points || []
  const legend = paletteLegend.length ? paletteLegend : (view?.legend || [])
  const classByKey = new Map(legend.map((item, index) => [item.key, index % 7]))
  const max = Math.max(1, ...points.flatMap((point) => [Number(point.current || 0), Number(point.previous || 0)]))
  const middle = max / 2

  function renderStack(point, index, series) {
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
          role={onSegmentActivate ? 'button' : undefined}
          tabIndex={onSegmentActivate ? 0 : undefined}
          className={'rz-dashboard-stack-segment rz-dashboard-stack-segment--' + (classByKey.get(segment.key) ?? 0)}
          style={{ flexGrow: Math.max(0.0001, Number(segment.value || 0)) }}
          title={`${segment.label}: ${currency ? euro(segment.value) : numberLabel(segment.value)}`}
          aria-label={onSegmentActivate ? `${point.label}, ${segment.label}: ${currency ? euro(segment.value) : numberLabel(segment.value)}` : undefined}
          onPointerDown={onSegmentActivate ? (event) => event.stopPropagation() : undefined}
          onClick={onSegmentActivate ? (event) => {
            event.stopPropagation()
            onSegmentActivate(index, series, segment)
          } : undefined}
          onKeyDown={onSegmentActivate ? (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault()
              event.stopPropagation()
              onSegmentActivate(index, series, segment)
            }
          } : undefined}
        />
      ))}
    </span>
  }

  return <div className="rz-dashboard-comparison-chart rz-dashboard-stacked-chart" aria-label="Gestapelde uitgavengrafiek">
    <div className="rz-dashboard-y-axis" aria-hidden="true">
      <span>{compactAxis(max, currency)}</span>
      <span>{compactAxis(middle, currency)}</span>
      <span>{compactAxis(0, currency)}</span>
    </div>
    <div className="rz-dashboard-chart-plot">
      <div className="rz-dashboard-gridline rz-dashboard-gridline--top" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--mid" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--base" />
      <div className="rz-dashboard-comparison-bars">
        {points.map((point, index) => (
          <div className="rz-dashboard-comparison-group" key={point.label || index}>
            <div className="rz-dashboard-comparison-pair">
              {renderStack(point, index, 'previous')}
              {renderStack(point, index, 'current')}
            </div>
            <small>{point.label}</small>
          </div>
        ))}
      </div>
    </div>
  </div>
}

function ForecastChart({ values = [], onBarActivate = null }) {
  const max = Math.max(1, ...values.map((item) => Number(item.value || 0)))
  const middle = max / 2
  return <div className="rz-dashboard-comparison-chart rz-dashboard-forecast-chart" aria-label="Begrote uitgaven">
    <div className="rz-dashboard-y-axis" aria-hidden="true">
      <span>{compactAxis(max, true)}</span>
      <span>{compactAxis(middle, true)}</span>
      <span>€0</span>
    </div>
    <div className="rz-dashboard-chart-plot">
      <div className="rz-dashboard-gridline rz-dashboard-gridline--top" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--mid" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--base" />
      <div className="rz-dashboard-comparison-bars">
        {values.map((item, index) => (
          <div className="rz-dashboard-comparison-group" key={item.label || item.week || index}>
            <div className="rz-dashboard-comparison-pair rz-dashboard-comparison-pair--single">
              <span
                className="rz-dashboard-bar rz-dashboard-bar--current"
                role={onBarActivate ? 'button' : undefined}
                tabIndex={onBarActivate ? 0 : undefined}
                title={euro(item.value)}
                aria-label={onBarActivate ? `${item.label || ('W' + item.week)}, begrote uitgaven: ${euro(item.value)}` : undefined}
                onPointerDown={onBarActivate ? (event) => event.stopPropagation() : undefined}
                onClick={onBarActivate ? (event) => { event.stopPropagation(); onBarActivate(index, 'current', item) } : undefined}
                onKeyDown={onBarActivate ? (event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    event.stopPropagation()
                    onBarActivate(index, 'current', item)
                  }
                } : undefined}
                style={{ height: Math.max(3, Math.round((Number(item.value || 0) / max) * 100)) + '%' }}
              />
            </div>
            <small>{item.label || ('W' + item.week)}</small>
          </div>
        ))}
      </div>
    </div>
  </div>
}


function EmptyDashboardChart() {
  return <div className="rz-dashboard-comparison-chart" aria-label="Grafiek wordt opgebouwd" aria-busy="true">
    <div className="rz-dashboard-y-axis" aria-hidden="true">
      <span>–</span>
      <span>–</span>
      <span>0</span>
    </div>
    <div className="rz-dashboard-chart-plot">
      <div className="rz-dashboard-gridline rz-dashboard-gridline--top" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--mid" />
      <div className="rz-dashboard-gridline rz-dashboard-gridline--base" />
    </div>
  </div>
}

export default function MobileHomePage({ context, onOpenTile, welcomeText = 'Fijn dat je er weer bent.' }) {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [almostOutCount, setAlmostOutCount] = useState(null)
  const [pendingReceipts, setPendingReceipts] = useState(null)
  const [error, setError] = useState('')
  const [periodKey, setPeriodKey] = useState('days')
  const [cardOrder, setCardOrder] = useState(() => readDashboardCardOrder(context))
  const [draggingKey, setDraggingKey] = useState('')
  const dragStateRef = useRef(null)
  const suppressClickRef = useRef('')

  useEffect(() => {
    setCardOrder(readDashboardCardOrder(context))
  }, [context?.user_id])

  useEffect(() => {
    let active = true
    fetchHouseholdDashboard()
      .then((payload) => {
        if (!active) return
        setDashboard(payload)
        setError('')
      })
      .catch((exc) => {
        if (!active) return
        setError(exc?.message || 'Dashboard kon niet worden geladen.')
      })
    return () => { active = false }
  }, [context?.active_household_id, context?.user_id])

  useEffect(() => {
    let active = true
    setAlmostOutCount(null)
    setPendingReceipts(null)

    const householdId = String(context?.active_household_id || '').trim()
    if (householdId) {
      fetchAlmostOutCount(householdId)
        .then((count) => { if (active) setAlmostOutCount(count) })
        .catch(() => { if (active) setAlmostOutCount(null) })
    }

    fetchRetailerPendingReceiptSummary()
      .then((summary) => { if (active) setPendingReceipts(summary) })
      .catch(() => { if (active) setPendingReceipts({ count_available: false, pending_downloads: null }) })

    return () => { active = false }
  }, [context?.active_household_id, context?.user_id])

  const name = firstName(context) || 'gebruiker'
  const period = PERIODS.find((item) => item.key === periodKey) || PERIODS[0]

  const sharedFamilyLegend = useMemo(() => {
    if (!dashboard) return []
    const sources = [
      ...(dashboard.spend?.group_views?.[periodKey]?.legend || []),
      ...(dashboard.spend_year_over_year?.group_views?.[periodKey]?.legend || []),
    ]
    const unique = new Map()
    for (const item of sources) {
      const key = String(item?.key || '').trim()
      if (!key || unique.has(key)) continue
      unique.set(key, { key, label: item?.label || key })
    }
    return Array.from(unique.values()).slice(0, 7)
  }, [dashboard, periodKey])

  const cards = useMemo(() => {
    if (!dashboard) return []
    const yearSpendGroupView = dashboard.spend_year_over_year?.group_views?.[periodKey] || null
    const spendGroupView = dashboard.spend?.group_views?.[periodKey] || null
    const yearSpendPoints = (yearSpendGroupView?.points || dashboard.spend_year_over_year?.views?.[periodKey] || []).slice(-4)
    const spendPoints = (spendGroupView?.points || dashboard.spend?.views?.[periodKey] || dashboard.spend?.daily?.map((item) => ({
      label: String(item.date || '').slice(5),
      current: item.value,
      previous: 0,
    })) || []).slice(-4)
    const yearSpendCurrent = sumSeries(yearSpendPoints, 'current')
    const yearSpendPrevious = sumSeries(yearSpendPoints, 'previous')
    const spendCurrent = sumSeries(spendPoints, 'current')
    const spendPrevious = sumSeries(spendPoints, 'previous')
    const rawStoreView = dashboard.stores?.views?.[periodKey] || {
      current: { unique: dashboard.stores?.unique || 0, visits: dashboard.stores?.visits || 0 },
      previous: { unique: 0, visits: 0 },
      points: [],
    }
    const storeView = { ...rawStoreView, points: (rawStoreView.points || []).slice(-4) }
    const forecastPoints = (dashboard.forecast?.views?.[periodKey]
      || (dashboard.forecast?.weeks || []).map((item) => ({ label: 'W' + item.week, value: item.value }))).slice(0, 4)
    const forecastTotal = forecastPoints.reduce((total, item) => total + Number(item.value || 0), 0)
    const forecastPeriodLabel = periodKey === 'days'
      ? 'komende 4 dagen'
      : periodKey === 'weeks'
        ? 'komende 4 weken'
        : 'komende 4 maanden'

    return [
      {
        key: 'uitgaven-vorig-jaar',
        routeKey: 'uitgaven',
        title: 'Uitgaven t.o.v. vorig jaar',
        value: euro(yearSpendCurrent),
        detail: deltaText(yearSpendCurrent, yearSpendPrevious, euro, { previousLabel: 'dezelfde periode vorig jaar' }),
        chart: <StackedComparisonChart
          view={yearSpendGroupView || { points: yearSpendPoints, legend: [] }}
          currency
          paletteLegend={sharedFamilyLegend}
          onSegmentActivate={(index, series, segment) => openBarDrilldown('uitgaven', index, series, 'year', segment.key)}
        />,
      },
      {
        key: 'uitgaven',
        title: 'Uitgaven',
        value: euro(spendCurrent),
        detail: deltaText(spendCurrent, spendPrevious, euro, period),
        chart: <StackedComparisonChart
          view={spendGroupView || { points: spendPoints, legend: [] }}
          currency
          paletteLegend={sharedFamilyLegend}
          onSegmentActivate={(index, series, segment) => openBarDrilldown('uitgaven', index, series, 'previous', segment.key)}
        />,
      },
      {
        key: 'winkels',
        title: 'Bezochte winkels',
        value: numberLabel(storeView.current.unique) + ' winkels',
        detail: numberLabel(storeView.current.visits) + ' bezoeken · ' + deltaText(storeView.current.visits, storeView.previous.visits, numberLabel, period),
        chart: <ComparisonChart
          points={storeView.points || []}
          onBarActivate={(index, series) => openBarDrilldown('winkels', index, series, 'previous')}
        />,
      },
      {
        key: 'begroting',
        title: 'Begrote uitgaven',
        value: euro(forecastTotal),
        detail: 'herhalingskoop verwacht in de ' + forecastPeriodLabel,
        chart: <ForecastChart
          values={forecastPoints}
          onBarActivate={(index, series) => openBarDrilldown('begroting', index, series, 'previous')}
        />,
      },
    ]
  }, [dashboard, periodKey, period, sharedFamilyLegend])

  const orderedCards = useMemo(() => {
    const byKey = new Map(cards.map((card) => [card.key, card]))
    return cardOrder.map((key) => byKey.get(key)).filter(Boolean)
  }, [cards, cardOrder])

  const loadingCards = useMemo(() => ([
    { key: 'uitgaven-vorig-jaar', title: 'Uitgaven t.o.v. vorig jaar', value: '–', detail: 'Grafiek wordt opgebouwd', chart: <EmptyDashboardChart /> },
    { key: 'uitgaven', title: 'Uitgaven', value: '–', detail: 'Grafiek wordt opgebouwd', chart: <EmptyDashboardChart /> },
    { key: 'winkels', title: 'Bezochte winkels', value: '–', detail: 'Grafiek wordt opgebouwd', chart: <EmptyDashboardChart /> },
    { key: 'begroting', title: 'Begrote uitgaven', value: '–', detail: 'Grafiek wordt opgebouwd', chart: <EmptyDashboardChart /> },
  ]), [])
  const visibleCards = dashboard ? orderedCards : loadingCards

  function moveCard(draggedKey, targetKey) {
    if (!draggedKey || !targetKey || draggedKey === targetKey) return
    setCardOrder((current) => {
      const next = [...current]
      const fromIndex = next.indexOf(draggedKey)
      const toIndex = next.indexOf(targetKey)
      if (fromIndex < 0 || toIndex < 0) return current
      next.splice(fromIndex, 1)
      next.splice(toIndex, 0, draggedKey)
      writeDashboardCardOrder(next, context)
      return next
    })
  }

  function handleCardPointerDown(event, cardKey) {
    if (event.button != null && event.button !== 0) return
    if (!event.target.closest('.rz-dashboard-comparison-chart')) return
    dragStateRef.current = {
      cardKey,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    }
    setDraggingKey(cardKey)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  function handleCardPointerMove(event) {
    const state = dragStateRef.current
    if (!state || state.pointerId !== event.pointerId) return
    const distance = Math.hypot(event.clientX - state.startX, event.clientY - state.startY)
    if (distance >= 6) {
      state.moved = true
      event.preventDefault()
    }
    if (!state.moved) return
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest?.('[data-dashboard-card-key]')
    const targetKey = target?.getAttribute?.('data-dashboard-card-key') || ''
    if (targetKey && targetKey !== state.cardKey) moveCard(state.cardKey, targetKey)
  }

  function finishCardDrag(event) {
    const state = dragStateRef.current
    if (!state || state.pointerId !== event.pointerId) return
    if (state.moved) suppressClickRef.current = state.cardKey
    try { event.currentTarget.releasePointerCapture?.(event.pointerId) } catch {}
    dragStateRef.current = null
    setDraggingKey('')
  }

  function cancelCardDrag() {
    dragStateRef.current = null
    setDraggingKey('')
  }

  function openBarDrilldown(metric, bucketIndex, series, comparison = 'previous', groupKey = '') {
    const params = new URLSearchParams({
      granularity: periodKey,
      bucket: String(bucketIndex),
      series,
      comparison,
    })
    if (groupKey) params.set('group', groupKey)
    navigate('/dashboard/' + metric + '?' + params.toString())
  }

  function openCard(card) {
    if (suppressClickRef.current === card.key) {
      suppressClickRef.current = ''
      return
    }
    navigate('/dashboard/' + (card.routeKey || card.key))
  }

  function openStatus(key) {
    if (key === 'meldingen') return onOpenTile({ key: 'meldingen', clickable: true })
    if (key === 'winkelen') return onOpenTile({ key: 'winkelen', clickable: true })
    if (key === 'bonnen-open') return navigate('/kassa?view=bonnen')
    if (key === 'bonnen-downloaden') return navigate('/instellingen/winkelkoppelingen')
    if (key === 'bijna-op') return onOpenTile({ key: 'bijna-op', clickable: true })
    return undefined
  }

  return <main className="rz-mobile-home" data-testid="mobile-home-page">
    <MobileModuleHeader title="Dashboard" testId="mobile-home-header" />
    <section className="rz-mobile-home-inner">
      <h1 className="rz-mobile-home-welcome">Welkom {name} </h1>
      <p className="rz-mobile-home-subtitle">{welcomeText}</p>

      {error ? <div className="rz-dashboard-error" role="alert">{error}</div> : null}

      <div className="rz-dashboard-status" aria-label="Actuele status">
        <button type="button" onClick={() => openStatus('meldingen')} className="rz-dashboard-status--notifications" data-testid="dashboard-status-notifications">
          <strong>{dashboard?.status?.notifications ?? '–'}</strong>
          <span>Meldingen</span>
        </button>
        <button type="button" onClick={() => openStatus('winkelen')} className="rz-dashboard-status--shopping" data-testid="dashboard-status-shopping">
          <strong>{dashboard?.status?.shopping ?? '–'}</strong>
          <span>Boodschappen</span>
        </button>
        <button type="button" onClick={() => openStatus('bonnen-open')} className="rz-dashboard-status--open-receipts" data-testid="dashboard-status-open-receipts">
          <strong>{dashboard?.status?.put_away ?? '–'}</strong>
          <span>Bonnen open</span>
        </button>
        <button
          type="button"
          onClick={() => openStatus('bonnen-downloaden')}
          className="rz-dashboard-status--downloadable-receipts" data-testid="dashboard-status-downloadable-receipts"
          title={pendingReceipts?.count_available === false ? 'Aantal kon niet live worden opgehaald' : 'Nog te downloaden bonnen uit automatisch telbare winkelkoppelingen'}
        >
          <strong>{pendingReceipts?.count_available === false ? '–' : (pendingReceipts?.pending_downloads ?? '–')}</strong>
          <span>Bonnen downloaden</span>
        </button>
        <button type="button" onClick={() => openStatus('bijna-op')} className="rz-dashboard-status--almost-out" data-testid="dashboard-status-almost-out">
          <strong>{almostOutCount ?? '–'}</strong>
          <span>Bijna op</span>
        </button>
      </div>

      {!dashboard && !error ? <p role="status">Dashboard inlezen.</p> : null}

      <div className="rz-dashboard-period-switch" role="group" aria-label="Periode grafieken">
          {PERIODS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={periodKey === item.key ? 'is-active' : ''}
              aria-pressed={periodKey === item.key}
              onClick={() => setPeriodKey(item.key)}
              data-testid={'dashboard-period-' + item.key}
            >
              {item.label}
            </button>
          ))}
      </div>

      <section className="rz-dashboard-grid" aria-label="Huishoudoverzicht">
          {visibleCards.map((card) => (
            <button
              type="button"
              key={card.key}
              className={'rz-dashboard-card' + (draggingKey === card.key ? ' is-dragging' : '')}
              onClick={() => dashboard && openCard(card)}
              onPointerDown={dashboard ? (event) => handleCardPointerDown(event, card.key) : undefined}
              onPointerMove={dashboard ? handleCardPointerMove : undefined}
              onPointerUp={dashboard ? finishCardDrag : undefined}
              onPointerCancel={dashboard ? cancelCardDrag : undefined}
              aria-disabled={!dashboard}
              data-dashboard-card-key={card.key}
              data-testid={'dashboard-card-' + card.key}
            >
              <span className="rz-dashboard-card-title">{card.title}</span>
              <strong className="rz-dashboard-card-value">{card.value}</strong>
              <span className="rz-dashboard-card-detail">{card.detail}</span>
              {card.chart}
            </button>
          ))}
      </section>

      {dashboard ? <div className="rz-dashboard-shared-legend" aria-label="Legenda dashboardgrafieken">
          <div className="rz-dashboard-legend">
            <span><i className="rz-dashboard-legend-swatch rz-dashboard-legend-swatch--current" />Huidige periode</span>
            <span><i className="rz-dashboard-legend-swatch rz-dashboard-legend-swatch--previous" />Vergelijkingsperiode</span>
          </div>
          {sharedFamilyLegend.length ? <div className="rz-dashboard-stack-legend" aria-label="Productfamilies">
            {sharedFamilyLegend.map((item, index) => (
              <span key={item.key}>
                <i className={'rz-dashboard-stack-key rz-dashboard-stack-segment--' + (index % 7)} />
                {item.label}
              </span>
            ))}
          </div> : null}
      </div> : null}
    </section>
  </main>
}
