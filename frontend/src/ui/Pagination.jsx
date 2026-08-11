import Button from './Button.jsx'

export default function Pagination({ page = 1, pageCount = 1, onPageChange, disabled = false }) {
  const currentPage = Math.min(Math.max(Number(page) || 1, 1), Math.max(Number(pageCount) || 1, 1))
  const totalPages = Math.max(Number(pageCount) || 1, 1)

  if (totalPages <= 1) return null

  return (
    <nav aria-label="Paginering" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, marginTop: 10 }}>
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage <= 1}
        onClick={() => onPageChange?.(currentPage - 1)}
        aria-label="Vorige pagina"
      >
        ‹
      </Button>
      <span
        aria-current="page"
        style={{ minWidth: 32, height: 32, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
      >
        {currentPage}
      </span>
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || currentPage >= totalPages}
        onClick={() => onPageChange?.(currentPage + 1)}
        aria-label="Volgende pagina"
      >
        ›
      </Button>
    </nav>
  )
}
