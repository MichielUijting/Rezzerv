import Button from './Button.jsx'

export default function Pagination({ page = 1, pageCount = 1, onPageChange, disabled = false, labels = null }) {
  const currentPage = Math.min(Math.max(Number(page) || 1, 1), Math.max(Number(pageCount) || 1, 1))
  const totalPages = Math.max(Number(pageCount) || 1, 1)
  const navigationDisabled = disabled || totalPages <= 1
  const resolvedLabels = {
    first: labels?.first ?? '1',
    previous: labels?.previous ?? '−',
    next: labels?.next ?? '+',
    last: labels?.last ?? (Number.isFinite(Number(pageCount)) && Number(pageCount) > 0 ? String(totalPages) : 'Einde'),
  }

  return (
    <nav
      aria-label="Paginering"
      className="rz-pagination"
      style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
    >
      <Button
        type="button"
        variant="secondary"
        disabled={navigationDisabled || currentPage <= 1}
        onClick={() => onPageChange?.(1)}
      >
        {resolvedLabels.first}
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={navigationDisabled || currentPage <= 1}
        onClick={() => onPageChange?.(currentPage - 1)}
      >
        {resolvedLabels.previous}
      </Button>
      <span className="rz-pagination-page-indicator" aria-current="page">
        Pagina {currentPage} van {totalPages}
      </span>
      <Button
        type="button"
        variant="secondary"
        disabled={navigationDisabled || currentPage >= totalPages}
        onClick={() => onPageChange?.(currentPage + 1)}
      >
        {resolvedLabels.next}
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={navigationDisabled || currentPage >= totalPages}
        onClick={() => onPageChange?.(totalPages)}
      >
        {resolvedLabels.last}
      </Button>
    </nav>
  )
}
