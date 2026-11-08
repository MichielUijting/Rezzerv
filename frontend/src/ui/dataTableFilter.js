// Central DataTable filter terms. Only the complete reserved token is special;
// a normal (including '=') query continues using case-insensitive contains.
export function normalizeTableFilterText(value) {
  return String(value ?? '').trim().toLocaleLowerCase('nl')
}

export function isEmptyTableCell(value) {
  if (value == null) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

export function matchesTableFilter(value, filter) {
  const term = normalizeTableFilterText(filter)
  if (!term) return true
  if (term === '=leeg') return isEmptyTableCell(value)
  if (term === '=nietleeg') return !isEmptyTableCell(value)
  return normalizeTableFilterText(value).includes(term)
}
