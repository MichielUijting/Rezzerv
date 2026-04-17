const DEFAULT_SEPARATOR = ';'

function escapeCsvValue(value, separator = DEFAULT_SEPARATOR) {
  const text = String(value ?? '')
  const needsQuotes = text.includes('"') || text.includes('\n') || text.includes('\r') || text.includes(separator)
  const escaped = text.replace(/"/g, '""')
  return needsQuotes ? `"${escaped}"` : escaped
}

function formatTimestamp(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${year}${month}${day}-${hours}${minutes}${seconds}`
}

export function createCsvContent(columns = [], rows = [], separator = DEFAULT_SEPARATOR) {
  const headerRow = columns.map((column) => escapeCsvValue(column?.label ?? '', separator)).join(separator)
  const dataRows = rows.map((row) => columns.map((column) => {
    const value = typeof column?.getValue === 'function' ? column.getValue(row) : row?.[column?.key]
    return escapeCsvValue(value, separator)
  }).join(separator))
  return ['\ufeff' + headerRow, ...dataRows].join('\r\n')
}

export function downloadCsv({ columns = [], rows = [], filenamePrefix = 'rezzerv-export', separator = DEFAULT_SEPARATOR }) {
  const csv = createCsvContent(columns, rows, separator)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filenamePrefix}-${formatTimestamp()}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 0)
  return { filename: link.download, rowCount: rows.length }
}
