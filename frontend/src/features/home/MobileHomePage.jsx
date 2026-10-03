import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { fetchHouseholdDashboard } from './dashboardApi.js'
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

function InHuisWordmark() {
  return <span className="rz-inhuis-wordmark" aria-label="InHuis"><span className="rz-inhuis-wordmark-in">In</span><span className="rz-inhuis-wordmark-huis">Huis</span></span>
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

function ComparisonChart({ points = [], currency = false }) {
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
                title={'Vorige periode: ' + (currency ? euro(point.previous) : numberLabel(point.previous))}
                style={{ height: Math.max(3, Math.round((Number(point.previous || 0) / max) * 100)) + '%' }}
              />
              <span
                className="rz-dashboard-bar rz-dashboard-bar--current"
                title={'Huidige periode: ' + (currency ? euro(point.current) : numberLabel(point.current))}
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

function ForecastChart({ values = [] }) {
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
                title={euro(item.value)}
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

export default function MobileHomePage({ context, onOpenTile, welcomeText = 'Fijn dat je er weer bent.' }) {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [periodKey, setPeriodKey] = useState('days')

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

  const name = firstName(context) || 'gebruiker'
  const period = PERIODS.find((item) => item.key === periodKey) || PERIODS[0]

  const cards = useMemo(() => {
    if (!dashboard) return []
    const yearSpendPoints = (dashboard.spend_year_over_year?.views?.[periodKey] || []).slice(-4)
    const spendPoints = (dashboard.spend?.views?.[periodKey] || dashboard.spend?.daily?.map((item) => ({
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
        chart: <ComparisonChart points={yearSpendPoints} currency />,
      },
      {
        key: 'uitgaven',
        title: 'Uitgaven',
        value: euro(spendCurrent),
        detail: deltaText(spendCurrent, spendPrevious, euro, period),
        chart: <ComparisonChart points={spendPoints} currency />,
      },
      {
        key: 'winkels',
        title: 'Bezochte winkels',
        value: numberLabel(storeView.current.unique) + ' winkels',
        detail: numberLabel(storeView.current.visits) + ' bezoeken · ' + deltaText(storeView.current.visits, storeView.previous.visits, numberLabel, period),
        chart: <ComparisonChart points={storeView.points || []} />,
      },
      {
        key: 'begroting',
        title: 'Begrote uitgaven',
        value: euro(forecastTotal),
        detail: 'herhalingskoop verwacht in de ' + forecastPeriodLabel,
        chart: <ForecastChart values={forecastPoints} />,
      },
    ]
  }, [dashboard, periodKey, period])

  function openStatus(key) {
    if (key === 'meldingen') return onOpenTile({ key: 'meldingen', clickable: true })
    if (key === 'winkelen') return onOpenTile({ key: 'winkelen', clickable: true })
    if (key === 'opbergen') return navigate('/kassa?view=bonnen')
    return onOpenTile({ key: 'kassabonnen', clickable: true })
  }

  return <main className="rz-mobile-home" data-testid="mobile-home-page">
    <MobileModuleHeader title="Dashboard" testId="mobile-home-header" />
    <section className="rz-mobile-home-inner">
      <h1 className="rz-mobile-home-welcome">Welkom {name} <InHuisWordmark /></h1>
      <p className="rz-mobile-home-subtitle">{welcomeText}</p>

      {error ? <div className="rz-dashboard-error" role="alert">{error}</div> : null}

      <div className="rz-dashboard-status" aria-label="Actuele status">
        <button type="button" onClick={() => openStatus('meldingen')} data-testid="dashboard-status-notifications">
          <strong>{dashboard?.status?.notifications ?? '–'}</strong>
          <span>Meldingen</span>
        </button>
        <button type="button" onClick={() => openStatus('winkelen')} data-testid="dashboard-status-shopping">
          <strong>{dashboard?.status?.shopping ?? '–'}</strong>
          <span>Boodschappen</span>
        </button>
        <button type="button" onClick={() => openStatus('opbergen')} data-testid="dashboard-status-put-away">
          <strong>{dashboard?.status?.put_away ?? '–'}</strong>
          <span>Nog opbergen</span>
        </button>
      </div>

      {!dashboard && !error ? <p role="status">Dashboard inlezen.</p> : null}

      {dashboard ? <>
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

        <div className="rz-dashboard-legend" aria-label="Legenda">
          <span><i className="rz-dashboard-legend-swatch rz-dashboard-legend-swatch--current" />Huidige periode</span>
          <span><i className="rz-dashboard-legend-swatch rz-dashboard-legend-swatch--previous" />Vergelijkingsperiode</span>
        </div>

        <section className="rz-dashboard-grid" aria-label="Huishoudoverzicht">
          {cards.map((card) => (
            <button
              type="button"
              key={card.key}
              className="rz-dashboard-card"
              onClick={() => navigate('/dashboard/' + (card.routeKey || card.key))}
              data-testid={'dashboard-card-' + card.key}
            >
              <span className="rz-dashboard-card-title">{card.title}</span>
              <strong className="rz-dashboard-card-value">{card.value}</strong>
              <span className="rz-dashboard-card-detail">{card.detail}</span>
              {card.chart}
            </button>
          ))}
        </section>
      </> : null}
    </section>
  </main>
}
