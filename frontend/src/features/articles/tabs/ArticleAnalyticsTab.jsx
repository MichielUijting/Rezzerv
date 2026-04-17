import { useEffect, useMemo, useState } from 'react'
import { ArticleGlobalSectionToggle, ArticleSectionAccordion } from '../components/ArticleSectionControls'
import { AUTO_CONSUME_MODES, fetchArticleAutoConsumeMode, getArticleAutoConsumeMode } from '../services/articleAutomationOverrideService'
import { fetchHouseholdAutomationSettings, getHouseholdAutomationSettings } from '../../settings/services/householdAutomationService'

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

function getWeekStart(date) {
  const normalized = new Date(date)
  normalized.setHours(0, 0, 0, 0)
  const day = normalized.getDay()
  const diff = day === 0 ? -6 : 1 - day
  normalized.setDate(normalized.getDate() + diff)
  return normalized
}

function getQuarterLabel(date) {
  const quarter = Math.floor(date.getMonth() / 3) + 1
  return `K${quarter} ${date.getFullYear()}`
}

function getWeekLabel(date) {
  const weekStart = getWeekStart(date)
  return formatDate(weekStart.toISOString())
}

function buildChartBuckets(history, period = 'month') {
  const relevant = history.filter((entry) => entry?.type === 'Aankoop' || entry?.type === 'Verbruik')
  if (!relevant.length) return []

  const buckets = new Map()
  relevant.forEach((entry) => {
    const date = new Date(entry.datetime)
    if (Number.isNaN(date.getTime())) return

    let key = ''
    let label = ''
    if (period === 'week') {
      const weekStart = getWeekStart(date)
      key = `W-${weekStart.getFullYear()}-${String(weekStart.getMonth() + 1).padStart(2, '0')}-${String(weekStart.getDate()).padStart(2, '0')}`
      label = getWeekLabel(date)
    } else if (period === 'quarter') {
      key = `Q-${date.getFullYear()}-${Math.floor(date.getMonth() / 3) + 1}`
      label = getQuarterLabel(date)
    } else {
      key = `M-${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      label = new Intl.DateTimeFormat('nl-NL', { month: 'short', year: 'numeric' }).format(date)
    }

    if (!buckets.has(key)) {
      buckets.set(key, { label, purchases: 0, consumes: 0 })
    }
    const bucket = buckets.get(key)
    if (entry.type === 'Aankoop') bucket.purchases += Number(entry.quantity_change || 0)
    if (entry.type === 'Verbruik') bucket.consumes += Number(entry.quantity_change || 0)
  })

  return Array.from(buckets.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([, value]) => value)
    .slice(-8)
}


function AnalyticsRows({ rows = [] }) {
  return (
    <div className="rz-analytics-card-body rz-article-detail-section-body">
      {rows.map((row) => (
        <div key={row.label} className="rz-analytics-row">
          <div className="rz-analytics-row-label">{row.label}</div>
          <div className="rz-analytics-row-value">{row.value}</div>
        </div>
      ))}
    </div>
  )
}

function AnalyticsChartBody({ buckets, period, onPeriodChange }) {
  if (!buckets.length) {
    return <div className="rz-empty-state">Nog onvoldoende mutaties voor een tijdgrafiek.</div>
  }

  const maxValue = Math.max(1, ...buckets.flatMap((bucket) => [bucket.purchases, bucket.consumes]))

  return (
    <>
      <div className="rz-analytics-period-switch" role="tablist" aria-label="Periodekeuze grafiek">
          {[
            { key: 'week', label: 'Week' },
            { key: 'month', label: 'Maand' },
            { key: 'quarter', label: 'Kwartaal' },
          ].map((option) => (
            <button
              key={option.key}
              type="button"
              className={`rz-analytics-period-button ${period === option.key ? 'is-active' : ''}`}
              onClick={() => onPeriodChange(option.key)}
              aria-pressed={period === option.key}
            >
              {option.label}
            </button>
          ))}
      </div>
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
    </>
  )
}

function isConsumable(articleData = {}) {
  if (articleData.consumable === true) return true
  return articleData.article_type === 'Voedsel & drank' || articleData.type === 'Voedsel & drank' || articleData.article_type === 'Huishoudelijk' || articleData.type === 'Huishoudelijk'
}

function getAutoConsumeModeLabel(mode) {
  if (mode === AUTO_CONSUME_MODES.ALWAYS_ON) return 'Altijd automatisch afboeken'
  if (mode === AUTO_CONSUME_MODES.ALWAYS_OFF) return 'Nooit automatisch afboeken'
  return 'Huishoudinstelling volgen'
}

export default function ArticleAnalyticsTab({ articleData = {} }) {
  const [period, setPeriod] = useState('month')
  const [householdSettings, setHouseholdSettings] = useState(() => getHouseholdAutomationSettings())
  const [articleMode, setArticleMode] = useState(() => getArticleAutoConsumeMode(articleData?.id))
  const analyticsSectionIds = ['chart', 'automation', 'price', 'consumption', 'forecast', 'advice', 'quality']
  const [sectionStates, setSectionStates] = useState(() => analyticsSectionIds.reduce((acc, sectionId) => ({ ...acc, [sectionId]: true }), {}))
  const locations = Array.isArray(articleData.locations) ? articleData.locations : []
  const history = Array.isArray(articleData.history) ? getSortedHistory(articleData.history) : []
  const backendPriceSummary = articleData.price_summary || {}
  const backendPriceHistory = Array.isArray(articleData.price_history) ? articleData.price_history : []

  useEffect(() => {
    let cancelled = false

    async function syncAutomationState() {
      const [nextHousehold, nextMode] = await Promise.all([
        fetchHouseholdAutomationSettings(),
        fetchArticleAutoConsumeMode(articleData?.id),
      ])
      if (cancelled) return
      setHouseholdSettings(nextHousehold || getHouseholdAutomationSettings())
      setArticleMode(nextMode || getArticleAutoConsumeMode(articleData?.id))
    }

    syncAutomationState()
    window.addEventListener('rezzerv-household-automation-updated', syncAutomationState)
    window.addEventListener('rezzerv-article-auto-consume-overrides-updated', syncAutomationState)

    return () => {
      cancelled = true
      window.removeEventListener('rezzerv-household-automation-updated', syncAutomationState)
      window.removeEventListener('rezzerv-article-auto-consume-overrides-updated', syncAutomationState)
    }
  }, [articleData?.id])

  const analytics = useMemo(() => {
    const totalQuantity = locations.reduce((sum, entry) => sum + (Number(entry?.aantal) || 0), 0)
    const computedPriceInsights = buildPriceInsights(history)
    const priceInsights = {
      lowestPrice: computedPriceInsights.lowestPrice,
      cheapestStore: backendPriceSummary.latest_store || computedPriceInsights.cheapestStore,
      averagePrice: backendPriceSummary.average_price != null ? formatCurrency(backendPriceSummary.average_price) : computedPriceInsights.averagePrice,
      latestPrice: backendPriceSummary.latest_price != null ? formatCurrency(backendPriceSummary.latest_price) : computedPriceInsights.latestPrice,
      latestStore: backendPriceSummary.latest_store || "Onbekend",
      latestPurchaseDate: backendPriceSummary.latest_purchase_date ? formatDate(backendPriceSummary.latest_purchase_date) : "—",
      historyCount: backendPriceHistory.length || Number(backendPriceSummary.history_count || 0),
    }
    const consumption = buildConsumptionInsights(history)
    const forecast = buildRunoutForecast(totalQuantity, consumption.weeklyValue)
    const latestEvent = history.length ? history[history.length - 1] : null
    const recommendation = buildRecommendation(priceInsights, forecast, articleData.name || 'dit artikel')
    const chartBuckets = buildChartBuckets(history)

    const consumable = isConsumable(articleData)
    const effectiveAutomation = !consumable
      ? 'Niet van toepassing'
      : articleMode === AUTO_CONSUME_MODES.ALWAYS_ON
        ? 'Actief via artikeloverride'
        : articleMode === AUTO_CONSUME_MODES.ALWAYS_OFF
          ? 'Geblokkeerd via artikeloverride'
          : householdSettings.autoConsumeOnRepurchase
            ? 'Actief via huishoudinstelling'
            : 'Uit via huishoudinstelling'

    return {
      automation: [
        { label: 'Artikeloverride', value: getAutoConsumeModeLabel(articleMode) },
        { label: 'Huishoudinstelling', value: householdSettings.autoConsumeOnRepurchase ? 'Aan' : 'Uit' },
        { label: 'Effectieve automatische afboeking', value: effectiveAutomation },
      ],
      price: [
        { label: 'Laagste bekende prijs', value: priceInsights.lowestPrice },
        { label: 'Winkel met laagste prijs', value: priceInsights.cheapestStore },
        { label: 'Gemiddelde prijs', value: priceInsights.averagePrice },
        { label: 'Laatste aankoopprijs', value: priceInsights.latestPrice },
        { label: 'Laatste winkel', value: priceInsights.latestStore },
        { label: 'Datum laatste aankoop', value: priceInsights.latestPurchaseDate },
        { label: 'Aantal prijsmetingen', value: String(priceInsights.historyCount || 0) },
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
      chartBuckets: buildChartBuckets(history, period),
      quality: [
        { label: 'Laatste mutatie', value: latestEvent ? formatDateTime(latestEvent.datetime) : '—' },
        { label: 'Laatste bron', value: latestEvent?.source || '—' },
        { label: 'Aantal locaties', value: String(locations.length) },
      ],
    }
  }, [articleData, articleMode, householdSettings, history, locations, period])


  const canExpandAll = analyticsSectionIds.some((sectionId) => sectionStates[sectionId] === false)
  const canCollapseAll = analyticsSectionIds.some((sectionId) => sectionStates[sectionId] !== false)

  function toggleSection(sectionId) {
    setSectionStates((current) => ({ ...current, [sectionId]: !current[sectionId] }))
  }

  function expandAllSections() {
    setSectionStates((current) => analyticsSectionIds.reduce((acc, sectionId) => ({ ...acc, [sectionId]: true }), { ...current }))
  }

  function collapseAllSections() {
    setSectionStates((current) => analyticsSectionIds.reduce((acc, sectionId) => ({ ...acc, [sectionId]: false }), { ...current }))
  }

  return (
    <div className="rz-analytics-tab" data-testid="analysis-page">
      <ArticleGlobalSectionToggle ariaLabelPrefix="Analyse" onExpandAll={expandAllSections} onCollapseAll={collapseAllSections} canExpand={canExpandAll} canCollapse={canCollapseAll} />
      <ArticleSectionAccordion title="Aankoop en verbruik in de tijd" open={sectionStates.chart} onToggle={() => toggleSection('chart')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
        <AnalyticsChartBody buckets={analytics.chartBuckets} period={period} onPeriodChange={setPeriod} />
      </ArticleSectionAccordion>
      <div data-testid="analysis-row-automation">
        <ArticleSectionAccordion title="Automatisering" open={sectionStates.automation} onToggle={() => toggleSection('automation')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <AnalyticsRows rows={analytics.automation} />
        </ArticleSectionAccordion>
      </div>
      <div data-testid="analysis-row-price">
        <ArticleSectionAccordion title="Prijsinzichten" open={sectionStates.price} onToggle={() => toggleSection('price')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <AnalyticsRows rows={analytics.price} />
        </ArticleSectionAccordion>
      </div>
      <div data-testid="analysis-row-consumption">
        <ArticleSectionAccordion title="Verbruiksbeeld" open={sectionStates.consumption} onToggle={() => toggleSection('consumption')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <AnalyticsRows rows={analytics.consumption} />
        </ArticleSectionAccordion>
      </div>
      <div data-testid="analysis-row-forecast">
        <ArticleSectionAccordion title="Voorraadprognose" open={sectionStates.forecast} onToggle={() => toggleSection('forecast')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <AnalyticsRows rows={analytics.forecast} />
        </ArticleSectionAccordion>
      </div>
      <div data-testid="analysis-row-advice">
        <ArticleSectionAccordion title="Aanbeveling" open={sectionStates.advice} onToggle={() => toggleSection('advice')} sectionClassName="rz-analytics-accordion rz-article-detail-section rz-analytics-accordion--advice" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <p className="rz-analytics-advice-text">{analytics.recommendation}</p>
        </ArticleSectionAccordion>
      </div>
      <div data-testid="analysis-row-quality">
        <ArticleSectionAccordion title="Onderbouwing" open={sectionStates.quality} onToggle={() => toggleSection('quality')} sectionClassName="rz-analytics-accordion rz-article-detail-section" titleClassName="rz-analytics-card-title rz-article-detail-section-title" contentClassName="rz-analytics-accordion-content">
          <AnalyticsRows rows={analytics.quality} />
        </ArticleSectionAccordion>
      </div>
    </div>
  )
}