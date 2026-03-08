import { useMemo } from 'react'

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(Number(value))
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('nl-NL')
}

function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('nl-NL', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

function daysBetween(a, b) {
  return Math.max(0, (a - b) / (1000 * 60 * 60 * 24))
}

function getSortedHistory(history) {
  return [...history].sort((a, b) => new Date(a.datetime || 0) - new Date(b.datetime || 0))
}

function buildPriceInsights(history) {
  const purchases = history.filter((entry) => entry?.type === 'Aankoop' && typeof entry?.price === 'number')
  if (!purchases.length) {
    return {
      lowestPrice: '—',
      cheapestStore: 'Onbekend',
      averagePrice: '—',
      latestPrice: '—',
    }
  }

  const cheapest = purchases.reduce((best, entry) => (entry.price < best.price ? entry : best), purchases[0])
  const latest = [...purchases].sort((a, b) => new Date(b.datetime || 0) - new Date(a.datetime || 0))[0]
  const average = purchases.reduce((sum, entry) => sum + Number(entry.price || 0), 0) / purchases.length

  return {
    lowestPrice: formatCurrency(cheapest.price),
    cheapestStore: cheapest.store || 'Onbekend',
    averagePrice: formatCurrency(average),
    latestPrice: formatCurrency(latest.price),
  }
}

function buildConsumptionInsights(history) {
  const consumes = history.filter((entry) => entry?.type === 'Verbruik')
  if (!consumes.length) {
    return {
      perWeek: 'Nog onvoldoende verbruiksdata',
      weeklyValue: null,
      lastConsumptionAt: '—',
    }
  }

  const sorted = [...consumes].sort((a, b) => new Date(a.datetime || 0) - new Date(b.datetime || 0))
  const totalConsumed = sorted.reduce((sum, entry) => sum + Number(entry.quantity_change || 0), 0)
  const firstDate = new Date(sorted[0].datetime)
  const lastDate = new Date(sorted[sorted.length - 1].datetime)
  const periodDays = Math.max(7, daysBetween(lastDate, firstDate) || 7)
  const perWeek = (totalConsumed / periodDays) * 7

  return {
    perWeek: `${perWeek.toFixed(1)} stuks per week`,
    weeklyValue: perWeek,
    lastConsumptionAt: formatDate(sorted[sorted.length - 1].datetime),
  }
}

function buildRunoutForecast(totalQuantity, weeklyConsumption) {
  if (!weeklyConsumption || weeklyConsumption <= 0 || totalQuantity <= 0) {
    return {
      date: 'Niet te bepalen',
      daysLeft: '—',
      signal: totalQuantity > 0 ? 'Nog onvoldoende verbruiksdata' : 'Geen voorraad beschikbaar',
    }
  }

  const daysLeft = Math.round((totalQuantity / weeklyConsumption) * 7)
  const runout = new Date()
  runout.setDate(runout.getDate() + daysLeft)

  let signal = 'Op schema'
  if (daysLeft <= 7) signal = 'Binnen 1 week op'
  else if (daysLeft <= 14) signal = 'Binnen 2 weken op'

  return {
    date: formatDate(runout.toISOString()),
    daysLeft: `${daysLeft} dagen`,
    signal,
  }
}

function buildRecommendation(priceInsights, forecast, articleName) {
  if (forecast.signal === 'Binnen 1 week op') {
    return `Aanbevolen: koop ${articleName.toLowerCase()} deze week opnieuw in. ${priceInsights.cheapestStore !== 'Onbekend' ? `${priceInsights.cheapestStore} heeft nu de laagste bekende prijs.` : ''}`.trim()
  }
  if (forecast.signal === 'Binnen 2 weken op') {
    return `Plan een aanvulling binnen twee weken. ${priceInsights.cheapestStore !== 'Onbekend' ? `${priceInsights.cheapestStore} is momenteel het voordeligst.` : ''}`.trim()
  }
  return priceInsights.cheapestStore !== 'Onbekend'
    ? `${priceInsights.cheapestStore} heeft momenteel de laagste bekende prijs voor ${articleName.toLowerCase()}.`
    : `Nog onvoldoende prijsdata beschikbaar voor ${articleName.toLowerCase()}.`
}

function buildChartBuckets(history) {
  const relevant = history.filter((entry) => entry?.type === 'Aankoop' || entry?.type === 'Verbruik')
  if (!relevant.length) return []

  const buckets = new Map()
  relevant.forEach((entry) => {
    const date = new Date(entry.datetime)
    if (Number.isNaN(date.getTime())) return
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    if (!buckets.has(key)) {
      buckets.set(key, { label: formatDate(entry.datetime), purchases: 0, consumes: 0 })
    }
    const bucket = buckets.get(key)
    if (entry.type === 'Aankoop') bucket.purchases += Number(entry.quantity_change || 0)
    if (entry.type === 'Verbruik') bucket.consumes += Number(entry.quantity_change || 0)
  })

  return Array.from(buckets.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([, value]) => value)
    .slice(-6)
}

function AnalyticsAccordion({ title, rows = [], children = null, defaultOpen = false, variant = '' }) {
  return (
    <details className={`rz-analytics-accordion ${variant ? `rz-analytics-accordion--${variant}` : ''}`} open={defaultOpen}>
      <summary className="rz-analytics-accordion-summary">
        <span className="rz-analytics-card-title">{title}</span>
        <span className="rz-analytics-accordion-indicator" aria-hidden="true">▾</span>
      </summary>
      <div className="rz-analytics-accordion-content">
        {rows.length > 0 ? (
          <div className="rz-analytics-card-body">
            {rows.map((row) => (
              <div key={row.label} className="rz-analytics-row">
                <div className="rz-analytics-row-label">{row.label}</div>
                <div className="rz-analytics-row-value">{row.value}</div>
              </div>
            ))}
          </div>
        ) : null}
        {children}
      </div>
    </details>
  )
}

function AnalyticsChart({ buckets }) {
  if (!buckets.length) {
    return <div className="rz-empty-state">Nog onvoldoende mutaties voor een tijdgrafiek.</div>
  }

  const maxValue = Math.max(1, ...buckets.flatMap((bucket) => [bucket.purchases, bucket.consumes]))

  return (
    <section className="rz-analytics-card">
      <h3 className="rz-analytics-card-title">Aankoop en verbruik in de tijd</h3>
      <div className="rz-analytics-chart">
        {buckets.map((bucket) => {
          const purchaseHeight = `${(bucket.purchases / maxValue) * 100}%`
          const consumeHeight = `${(bucket.consumes / maxValue) * 100}%`
          return (
            <div key={bucket.label} className="rz-analytics-chart-group">
              <div className="rz-analytics-chart-bars">
                <div className="rz-analytics-chart-bar-wrap">
                  <div className="rz-analytics-chart-bar rz-analytics-chart-bar--purchase" style={{ height: purchaseHeight }} title={`Aankoop: ${bucket.purchases}`} />
                </div>
                <div className="rz-analytics-chart-bar-wrap">
                  <div className="rz-analytics-chart-bar rz-analytics-chart-bar--consume" style={{ height: consumeHeight }} title={`Verbruik: ${bucket.consumes}`} />
                </div>
              </div>
              <div className="rz-analytics-chart-label">{bucket.label}</div>
            </div>
          )
        })}
      </div>
      <div className="rz-analytics-chart-legend">
        <span><i className="rz-analytics-chart-swatch rz-analytics-chart-swatch--purchase" /> Aankoop</span>
        <span><i className="rz-analytics-chart-swatch rz-analytics-chart-swatch--consume" /> Verbruik</span>
      </div>
    </section>
  )
}

export default function ArticleAnalyticsTab({ articleData = {} }) {
  const locations = Array.isArray(articleData.locations) ? articleData.locations : []
  const history = Array.isArray(articleData.history) ? getSortedHistory(articleData.history) : []

  const analytics = useMemo(() => {
    const totalQuantity = locations.reduce((sum, entry) => sum + (Number(entry?.aantal) || 0), 0)
    const priceInsights = buildPriceInsights(history)
    const consumption = buildConsumptionInsights(history)
    const forecast = buildRunoutForecast(totalQuantity, consumption.weeklyValue)
    const latestEvent = history.length ? history[history.length - 1] : null
    const recommendation = buildRecommendation(priceInsights, forecast, articleData.name || 'dit artikel')
    const chartBuckets = buildChartBuckets(history)

    return {
      price: [
        { label: 'Laagste bekende prijs', value: priceInsights.lowestPrice },
        { label: 'Winkel met laagste prijs', value: priceInsights.cheapestStore },
        { label: 'Gemiddelde prijs', value: priceInsights.averagePrice },
        { label: 'Laatste aankoopprijs', value: priceInsights.latestPrice },
      ],
      consumption: [
        { label: 'Gemiddeld verbruik per week', value: consumption.perWeek },
        { label: 'Laatste verbruik', value: consumption.lastConsumptionAt },
        { label: 'Totale voorraad nu', value: String(totalQuantity) },
      ],
      forecast: [
        { label: 'Verwachte datum lege voorraad', value: forecast.date },
        { label: 'Resterende tijd', value: forecast.daysLeft },
        { label: 'Signaal', value: forecast.signal },
      ],
      recommendation,
      chartBuckets,
      quality: [
        { label: 'Laatste mutatie', value: latestEvent ? formatDateTime(latestEvent.datetime) : '—' },
        { label: 'Laatste bron', value: latestEvent?.source || '—' },
        { label: 'Aantal locaties', value: String(locations.length) },
      ],
    }
  }, [articleData.name, history, locations])

  return (
    <div className="rz-analytics-tab">
      <AnalyticsChart buckets={analytics.chartBuckets} />
      <AnalyticsAccordion title="Prijsinzichten" rows={analytics.price} />
      <AnalyticsAccordion title="Verbruiksbeeld" rows={analytics.consumption} />
      <AnalyticsAccordion title="Voorraadprognose" rows={analytics.forecast} />
      <AnalyticsAccordion title="Aanbeveling" variant="advice" defaultOpen>
        <p className="rz-analytics-advice-text">{analytics.recommendation}</p>
      </AnalyticsAccordion>
      <AnalyticsAccordion title="Onderbouwing" rows={analytics.quality} />
    </div>
  )
}
