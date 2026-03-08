import { useMemo } from 'react'

function formatDateTime(value) {
  if (!value) return 'Onbekend moment'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('nl-NL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function countByType(history) {
  return history.reduce((acc, entry) => {
    const key = String(entry?.type || '').toLowerCase()
    if (!key) return acc
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
}

function getLatestEntry(history) {
  if (!history.length) return null
  return [...history].sort((a, b) => new Date(b.datetime || 0) - new Date(a.datetime || 0))[0]
}

function buildStockSignal(totalQuantity, locationCount) {
  if (totalQuantity <= 0) return 'Geen voorraad beschikbaar'
  if (totalQuantity <= 2) return 'Lage voorraad'
  if (locationCount > 1) return 'Voorraad gespreid over meerdere locaties'
  return 'Voorraad op niveau'
}

function buildUsageSignal(articleType, latestType, historyCount) {
  if (articleType === 'Gereedschap') {
    return historyCount >= 2 ? 'Activiteit geregistreerd in gebruiksgeschiedenis' : 'Beperkte gebruiksgeschiedenis'
  }

  if (latestType === 'Verbruik') return 'Recent verbruik geregistreerd'
  if (latestType === 'Aankoop') return 'Recent aangevuld'
  if (latestType === 'Correctie') return 'Recent handmatig aangepast'
  return 'Nog beperkt gebruiksbeeld beschikbaar'
}

function buildMetadataScore(articleData, history) {
  let score = 0
  const checks = [
    articleData?.brand,
    articleData?.barcode,
    articleData?.category,
    articleData?.subcategory,
    articleData?.weight,
    Array.isArray(articleData?.locations) && articleData.locations.length > 0,
    history.length > 0,
  ]

  checks.forEach((value) => {
    if (value) score += 1
  })

  if (score >= 7) return 'Hoog'
  if (score >= 5) return 'Goed'
  if (score >= 3) return 'Basis'
  return 'Beperkt'
}

function uniqueSources(history) {
  return [...new Set(history.map((entry) => entry?.source).filter(Boolean))]
}

function AnalysisCard({ title, rows }) {
  return (
    <section className="rz-analytics-card">
      <h3 className="rz-analytics-card-title">{title}</h3>
      <div className="rz-analytics-card-body">
        {rows.map((row) => (
          <div key={row.label} className="rz-analytics-row">
            <div className="rz-analytics-row-label">{row.label}</div>
            <div className="rz-analytics-row-value">{row.value}</div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function ArticleAnalyticsTab({ articleData = {} }) {
  const locations = Array.isArray(articleData.locations) ? articleData.locations : []
  const history = Array.isArray(articleData.history) ? articleData.history : []

  const analytics = useMemo(() => {
    const totalQuantity = locations.reduce((sum, entry) => sum + (Number(entry?.aantal) || 0), 0)
    const locationCount = locations.length
    const counts = countByType(history)
    const latestEntry = getLatestEntry(history)
    const sources = uniqueSources(history)
    const metadataScore = buildMetadataScore(articleData, history)

    return {
      stock: [
        { label: 'Status', value: buildStockSignal(totalQuantity, locationCount) },
        { label: 'Totale voorraad', value: String(totalQuantity) },
        { label: 'Aantal locaties', value: String(locationCount) },
      ],
      mutations: [
        { label: 'Signaal', value: history.length >= 3 ? 'Meerdere mutaties geregistreerd' : 'Beperkte mutatiehistorie' },
        { label: 'Totaal gebeurtenissen', value: String(history.length) },
        { label: 'Aankopen', value: String(counts['aankoop'] || 0) },
        { label: 'Verbruik', value: String(counts['verbruik'] || 0) },
        { label: 'Correcties', value: String(counts['correctie'] || 0) },
      ],
      usage: [
        { label: 'Gebruikssignaal', value: buildUsageSignal(articleData.type, latestEntry?.type, history.length) },
        { label: 'Laatste mutatie', value: latestEntry ? formatDateTime(latestEntry.datetime) : 'Nog geen mutaties' },
        { label: 'Laatste bron', value: latestEntry?.source || 'Onbekend' },
      ],
      quality: [
        { label: 'Metadata score', value: metadataScore },
        { label: 'Gebruikte bronnen', value: sources.length ? sources.join(', ') : 'Nog geen bronnen bekend' },
      ],
    }
  }, [articleData, history, locations])

  return (
    <div className="rz-analytics-tab">
      <AnalysisCard title="Voorraadsignaal" rows={analytics.stock} />
      <AnalysisCard title="Mutatiebeeld" rows={analytics.mutations} />
      <AnalysisCard title="Gebruiksbeeld" rows={analytics.usage} />
      <AnalysisCard title="Datakwaliteit" rows={analytics.quality} />
    </div>
  )
}
