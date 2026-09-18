import { limitSearchCandidates } from './searchCandidatePolicy.js'
import './searchCandidateList.css'

export default function SearchCandidateList({
  items = [],
  selectedKey = '',
  getKey = (item) => item?.id ?? item?.value ?? '',
  getLabel = (item) => item?.label ?? item?.name ?? '',
  onSelect,
  loading = false,
  emptyMessage = '',
  ariaLabel = 'Zoekresultaten',
  dataTestId = 'search-candidate-list',
}) {
  const visibleItems = limitSearchCandidates(items)

  if (loading) {
    return <div className="rz-search-candidate-status" role="status">Zoeken…</div>
  }

  if (visibleItems.length === 0) {
    return emptyMessage
      ? <div className="rz-search-candidate-status">{emptyMessage}</div>
      : null
  }

  return (
    <div
      id={dataTestId}
      className="rz-search-candidate-list"
      role="listbox"
      aria-label={ariaLabel}
      data-testid={dataTestId}
    >
      {visibleItems.map((item) => {
        const key = String(getKey(item) ?? '')
        const label = String(getLabel(item) ?? '')
        const selected = key === String(selectedKey ?? '')
        return (
          <button
            key={key || label}
            type="button"
            role="option"
            aria-selected={selected}
            className={`rz-search-candidate-option${selected ? ' rz-search-candidate-option--selected' : ''}`}
            onClick={() => onSelect?.(key, item)}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
