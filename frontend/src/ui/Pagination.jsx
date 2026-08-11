import Button from './Button.jsx'

export default function Pagination({ page = 1, pageCount = 1, onPageChange, disabled = false }) {
  const currentPage = Math.min(Math.max(Number(page) || 1, 1), Math.max(Number(pageCount) || 1, 1))
  const totalPages = Math.max(Number(pageCount) || 1, 1)

  if (totalPages <= 1) return null

  return (
    <nav
      aria-label="Paginering"
      className="rz-pagination"
      style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
    >
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage <= 1}
        onClick={() => onPageChange?.(1)}
      >
        Eerste
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage <= 1}
        onClick={() => onPageChange?.(currentPage - 1)}
      >
        Vorige
      </Button>
      <span className="rz-pagination-page-indicator" aria-current="page">
        Pagina {currentPage} van {totalPages}
      </span>
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage >= totalPages}
        onClick={() => onPageChange?.(currentPage + 1)}
      >
        Volgende
      </Button>
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage >= totalPages}
        onClick={() => onPageChange?.(totalPages)}
      >
        Laatste
      </Button>
    </nav>
  )
}
