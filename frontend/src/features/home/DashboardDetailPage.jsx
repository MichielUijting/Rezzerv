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

export default function DashboardDetailPage() {
  const { metric = '' } = useParams()
  const navigate = useNavigate()
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
        <div className="rz-dashboard-detail-summary"><strong>{dashboard.purchases.current} artikelen</strong><span>Vorige 7 dagen: {dashboard.purchases.previous}</span></div>
        <MiniBars values={dashboard.purchases.daily} />
      </>
    }
    if (definition.key === 'spend') {
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{euro(dashboard.spend.current)}</strong><span>Vorige 7 dagen: {euro(dashboard.spend.previous)}</span></div>
        <MiniBars values={dashboard.spend.daily} format={euro} />
      </>
    }
    if (definition.key === 'stores') {
      return <>
        <div className="rz-dashboard-detail-summary"><strong>{dashboard.stores.unique} winkels</strong><span>{dashboard.stores.visits} bezoeken</span></div>
        <div className="rz-dashboard-store-list">
          {(dashboard.stores.items || []).map((item) => <div key={item.name}><strong>{item.name}</strong><span>{item.visits} bezoek{item.visits === 1 ? '' : 'en'} · {euro(item.spend)}</span></div>)}
        </div>
      </>
    }
    return <>
      <div className="rz-dashboard-detail-summary"><strong>{euro(dashboard.forecast.total)}</strong><span>Komende 4 weken</span></div>
      <MiniBars values={dashboard.forecast.weeks} format={euro} />
      <p className="rz-dashboard-method">{dashboard.forecast.method}</p>
    </>
  }, [dashboard, definition.key])

  return <main className="rz-mobile-home" data-testid={'dashboard-detail-' + metric}>
    <MobileModuleHeader title={definition.title} testId="dashboard-detail-header" />
    <section className="rz-mobile-home-inner">
      {error ? <div role="alert" className="rz-dashboard-error">{error}</div> : null}
      {!dashboard && !error ? <p role="status">Dashboard laden…</p> : body}
      <button type="button" className="rz-dashboard-detail-close" onClick={() => navigate('/home')}>Terug naar dashboard</button>
    </section>
  </main>
}
