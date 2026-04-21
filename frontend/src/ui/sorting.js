const collator = new Intl.Collator('nl-NL', { numeric: true, sensitivity: 'base' })

function normalizeComparable(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return Number.isFinite(value) ? value : ''
  if (value instanceof Date) {
    const time = value.getTime()
    return Number.isNaN(time) ? '' : time
  }
  if (typeof value === 'boolean') return value ? 1 : 0
  return String(value).trim()
}

export function compareSortValues(left, right) {
  const a = normalizeComparable(left)
  const b = normalizeComparable(right)

  if (a === '' && b === '') return 0
  if (a === '') return 1
  if (b === '') return -1

  if (typeof a === 'number' && typeof b === 'number') return a - b
  return collator.compare(String(a), String(b))
}

export function nextSortState(current, key, defaultDirections = {}) {
  if (current?.key === key) {
    return { key, direction: current.direction === 'asc' ? 'desc' : 'asc' }
  }
  return { key, direction: defaultDirections[key] || 'asc' }
}

export function sortItems(items = [], sortState, accessors = {}) {
  if (!Array.isArray(items)) return []
  if (!sortState?.key || typeof accessors?.[sortState.key] !== 'function') return [...items]
  const direction = sortState.direction === 'desc' ? -1 : 1
  return [...items].sort((left, right) => {
    const result = compareSortValues(accessors[sortState.key](left), accessors[sortState.key](right))
    if (result !== 0) return result * direction
    return 0
  })
}

export function sortStringOptions(options = []) {
  return [...options].sort((left, right) => compareSortValues(left, right))
}

export function sortOptionObjects(options = [], labelAccessor = (option) => option?.label ?? option?.name ?? option?.value ?? '') {
  return [...options].sort((left, right) => compareSortValues(labelAccessor(left), labelAccessor(right)))
}
