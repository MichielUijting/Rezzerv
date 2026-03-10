import { useMemo } from "react"

function formatDateTime(value) {
  if (!value) return "Onbekend moment"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("nl-NL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function normalize(value, fallback = "—") {
  return value || fallback
}

function formatSource(value) {
  if (value === 'auto_repurchase') return 'Automatisch (herhaalaankoop)'
  if (value === 'store_import') return 'Winkelimport'
  return normalize(value)
}

function formatStoreImportProvider(note) {
  const value = String(note || '')
  const match = value.match(/(?:^|;)provider=([^;]+)/i)
  if (!match?.[1]) return null
  const provider = match[1].trim()
  if (!provider) return null
  return provider.charAt(0).toUpperCase() + provider.slice(1)
}

function formatNote(entry) {
  if (entry?.source === 'store_import') {
    const providerName = formatStoreImportProvider(entry?.note)
    return providerName ? `Geïmporteerd via ${providerName}` : 'Geïmporteerd via winkel'
  }
  return normalize(entry?.note)
}

export default function ArticleHistoryTab({ articleData = {} }) {
  const historyEntries = useMemo(() => {
    const items = Array.isArray(articleData.history) ? articleData.history : []
    return [...items].sort((a, b) => new Date(b.datetime || 0) - new Date(a.datetime || 0))
  }, [articleData.history])

  if (!historyEntries.length) {
    return <div className="rz-empty-state">Er is nog geen historie beschikbaar voor dit artikel.</div>
  }

  return (
    <div className="rz-history-tab">
      <section className="rz-history-group">
        <h3 className="rz-history-group-title">Voorraadhistorie</h3>
        <div className="rz-history-group-body">
          {historyEntries.map((entry, index) => (
            <article key={entry.id || `${entry.datetime || "moment"}-${entry.type || "event"}-${index}`} className="rz-history-card">
              <div className="rz-history-card-top">
                <div>
                  <div className="rz-history-card-datetime">{formatDateTime(entry.datetime)}</div>
                  <div className="rz-history-card-type">{normalize(entry.type, "Gebeurtenis")}</div>
                </div>
                <div className="rz-history-card-values">
                  <span>{normalize(entry.old_value)}</span>
                  <span aria-hidden="true">→</span>
                  <span>{normalize(entry.new_value)}</span>
                </div>
              </div>

              <div className="rz-history-card-meta">
                <div className="rz-history-meta-row">
                  <span className="rz-history-meta-label">Locatie</span>
                  <span className="rz-history-meta-value">{normalize(entry.location)}</span>
                </div>
                <div className="rz-history-meta-row">
                  <span className="rz-history-meta-label">Bron</span>
                  <span className={`rz-history-meta-value ${entry.source === 'auto_repurchase' ? 'rz-history-meta-value--auto' : ''}`}>{formatSource(entry.source)}</span>
                </div>
                <div className="rz-history-meta-row">
                  <span className="rz-history-meta-label">Opmerking</span>
                  <span className="rz-history-meta-value">{formatNote(entry)}</span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
