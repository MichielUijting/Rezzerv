import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import MobileModuleHeader from '../../ui/MobileModuleHeader.jsx'
import { fetchHouseholdDashboard } from './dashboardApi.js'
import './mobileHome.css'

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

function deltaLabel(value, unit = '') {
  const number = Number(value || 0)
  if (number === 0) return 'gelijk aan vorige 7 dagen'
  const sign = number > 0 ? '+' : '−'
  const absolute = Math.abs(number)
  return `${sign}${unit === 'EUR' ? euro(absolute) : absolute + (unit ? ' ' + unit : '')} t.o.v. vorige 7 dagen`
}

function Bars({ values = [] }) {
  const max = Math.max(1, ...values.map((item) => Number(item.value || 0)))
  return <div className="rz-dashboard-bars" aria-hidden="true">
    {values.map((item, index) => (
      <span key={item.date || item.week || index} style={{ height: Math.max(8, Math.round((Number(item.value || 0) / max) * 100)) + '%' }} />
    ))}
  </div>
}

export default function MobileHomePage({ context, onOpenTile, welcomeText = 'Fijn dat je er weer bent.' }) {
  const navigate = useNavigate()
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')

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
  const cards = useMemo(() => {
    if (!dashboard) return []
    return [
      {
        key: 'aankopen',
        title: 'Gekochte artikelen',
        value: `${dashboard.purchases.current} artikelen`,
        detail: deltaLabel(dashboard.purchases.delta, 'artikelen'),
        chart: <Bars values={dashboard.purchases.daily} />,
      },
      {
        key: 'uitgaven',
        title: 'Uitgaven',
        value: euro(dashboard.spend.current),
        detail: deltaLabel(dashboard.spend.delta, 'EUR'),
        chart: <Bars values={dashboard.spend.daily} />,
      },
      {
        key: 'winkels',
        title: 'Bezochte winkels',
        value: `${dashboard.stores.unique} winkels`,
        detail: `${dashboard.stores.visits} winkelbezoek${dashboard.stores.visits === 1 ? '' : 'en'} in 7 dagen`,
        chart: <div className="rz-dashboard-store-preview">{(dashboard.stores.items || []).slice(0, 3).map((item) => <span key={item.name}>{item.name} · {item.visits}</span>)}</div>,
      },
      {
        key: 'begroting',
        title: 'Begrote uitgaven',
        value: euro(dashboard.forecast.total),
        detail: 'verwacht voor de komende 4 weken',
        chart: <Bars values={dashboard.forecast.weeks} />,
      },
    ]
  }, [dashboard])

  function openStatus(key) {
    if (key === 'meldingen') return onOpenTile({ key: 'meldingen', clickable: true })
    if (key === 'winkelen') return onOpenTile({ key: 'winkelen', clickable: true })
    const routeKey = dashboard?.status?.put_away_route === '/kassa' ? 'kassa' : 'kassabonnen'
    return onOpenTile({ key: routeKey, clickable: true })
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

      {!dashboard && !error ? <p role="status">Dashboard laden…</p> : null}

      {dashboard ? <section className="rz-dashboard-grid" aria-label="Huishoudoverzicht">
        {cards.map((card) => (
          <button
            type="button"
            key={card.key}
            className="rz-dashboard-card"
            onClick={() => navigate('/dashboard/' + card.key)}
            data-testid={'dashboard-card-' + card.key}
          >
            <span className="rz-dashboard-card-title">{card.title}</span>
            <strong className="rz-dashboard-card-value">{card.value}</strong>
            <span className="rz-dashboard-card-detail">{card.detail}</span>
            {card.chart}
            <span className="rz-dashboard-card-link">Bekijk details ›</span>
          </button>
        ))}
      </section> : null}
    </section>
  </main>
}
