import Card from './Card.jsx'

function normalizeTrend(trend, currentValue) {
  const rows = Array.isArray(trend) ? trend.slice(-7) : []
  if (rows.length === 0) return []
  return rows.map((item) => ({
    date: String(item?.date || ''),
    value: Number.isFinite(Number(item?.value)) ? Number(item.value) : 0,
  })).map((item, index, all) => index === all.length - 1 ? { ...item, value: Number(currentValue ?? item.value) } : item)
}

function buildGeometry(rows) {
  if (rows.length === 0) return { line: '', area: '' }
  const values = rows.map((item) => item.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min
  const points = rows.map((item, index) => {
    const x = rows.length === 1 ? 50 : (index / (rows.length - 1)) * 100
    const y = range === 0 ? 29 : 50 - ((item.value - min) / range) * 42
    return { x, y }
  })
  const line = points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
  const area = `M 0 56 ${points.map((point) => `L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')} L 100 56 Z`
  return { line, area }
}

function growthPercentage(rows) {
  if (rows.length < 2) return null
  const start = Number(rows[0]?.value)
  const end = Number(rows[rows.length - 1]?.value)
  if (!Number.isFinite(start) || !Number.isFinite(end) || start === 0) return null
  return ((end - start) / Math.abs(start)) * 100
}

function formatGrowth(value) {
  if (value == null || !Number.isFinite(value)) return '—'
  if (Math.abs(value) < 0.05) return '0%'
  const rounded = Math.round(value * 10) / 10
  const formatted = Math.abs(rounded).toLocaleString('nl-NL', { maximumFractionDigits: 1 })
  return `${rounded > 0 ? '+' : '−'}${formatted}%`
}

export default function MetricTrendCard({ label, value, trend = [], detail = '', testId }) {
  const rows = normalizeTrend(trend, value)
  const { line, area } = buildGeometry(rows)
  const growth = growthPercentage(rows)
  const growthText = formatGrowth(growth)
  const trendLabel = rows.length === 7
    ? rows.map((item) => `${item.date}: ${item.value}`).join(', ')
    : 'Nog onvoldoende historische gegevens voor zeven kalenderdagen.'

  return (
    <Card>
      <div
        data-testid={testId}
        data-trend-points={rows.length}
        data-growth-percentage={growth == null ? '' : String(growth)}
        style={{ position: 'relative', minWidth: 150, minHeight: 132, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ position: 'relative', zIndex: 2, fontSize: 14, textAlign: 'center' }}>{label}</div>
        {rows.length > 0 ? (
          <svg
            viewBox="0 0 100 56"
            preserveAspectRatio="none"
            role="img"
            aria-label={`${label}, ontwikkeling afgelopen 7 kalenderdagen: ${trendLabel}`}
            style={{ position: 'absolute', zIndex: 0, left: -2, right: -2, bottom: 23, width: 'calc(100% + 4px)', height: 76, color: 'var(--color-brand-primary, #2e7d4d)', opacity: 0.28, pointerEvents: 'none' }}
          >
            <path d={area} fill="currentColor" opacity="0.30" />
            <path d={line} fill="none" stroke="currentColor" strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
          </svg>
        ) : null}
        <div style={{ position: 'relative', zIndex: 2, flex: 1, display: 'grid', placeItems: 'center', fontSize: 34, lineHeight: 1, fontWeight: 600, padding: '15px 42px 11px' }}>
          {value}
        </div>
        <div
          data-testid={testId ? `${testId}-growth` : undefined}
          aria-label={`${label}, groei afgelopen 7 kalenderdagen: ${growthText}`}
          title="Groei van eerste naar laatste kalenderdag in de getoonde 7-daagse periode"
          style={{ position: 'absolute', zIndex: 3, right: 8, top: '50%', transform: 'translateY(-16%)', minWidth: 38, textAlign: 'right', fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}
        >
          {growthText}
        </div>
        <div style={{ position: 'relative', zIndex: 2, minHeight: 18, fontSize: 12, textAlign: 'center' }}>
          {detail || 'Afgelopen 7 kalenderdagen'}
        </div>
      </div>
    </Card>
  )
}
