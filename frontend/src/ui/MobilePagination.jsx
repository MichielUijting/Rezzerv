import { useEffect, useMemo, useState } from 'react'
import Pagination from './Pagination.jsx'

export const MOBILE_PAGE_SIZE = 10

export function useMobilePagination(items = [], resetKey = '') {
  const safeItems = Array.isArray(items) ? items : []
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(safeItems.length / MOBILE_PAGE_SIZE))

  useEffect(() => {
    setPage(1)
  }, [resetKey])

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [page, pageCount])

  const pageItems = useMemo(() => {
    const start = (page - 1) * MOBILE_PAGE_SIZE
    return safeItems.slice(start, start + MOBILE_PAGE_SIZE)
  }, [safeItems, page])

  return { page, pageCount, pageItems, setPage }
}

export function MobilePaginationControls({ page, pageCount, setPage, ariaLabel = 'Paginering' }) {
  if (pageCount <= 1) return null
  return (
    <div className="rz-mobile-pagination" aria-label={ariaLabel}>
      <Pagination
        page={page}
        pageCount={pageCount}
        onPageChange={setPage}
        labels={{
          first: 'Eerste',
          previous: '−',
          next: '+',
          last: Number.isFinite(Number(pageCount)) && Number(pageCount) > 0 ? String(pageCount) : 'Einde',
        }}
      />
    </div>
  )
}
