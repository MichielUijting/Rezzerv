import { useMemo, useState } from 'react'
import Table from './Table'
import { buildTableWidth, ResizableHeaderCell, useResizableColumnWidths } from './resizableTable.jsx'
import { nextSortState, sortItems } from './sorting'

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase()
}

function defaultGetValue(row, column) {
  if (!row || !column?.key) return ''
  return row[column.key]
}

function buildDefaultWidths(columns) {
  return Object.fromEntries(
    columns.map((column) => [column.key, Number(column.width || 120)])
  )
}

function buildSortDefaults(columns, fallbackSort = null) {
  const defaults = {}

  columns.forEach((column) => {
    if (!column?.sortable) return
    defaults[column.key] = column.defaultDirection || (column.align === 'right' ? 'desc' : 'asc')
  })

  if (fallbackSort?.key && !defaults[fallbackSort.key]) {
    defaults[fallbackSort.key] = fallbackSort.direction || 'asc'
  }

  return defaults
}

export default function DataTable({
  columns = [],
  data = [],
  getRowKey = (row, index) => row?.id ?? row?.key ?? index,
  renderRow = null,
  defaultSort = null,
  emptyMessage = 'Geen gegevens gevonden.',
  wrapperClassName = '',
  tableClassName = '',
  dataTestId = undefined,
  stickyHeader = true,
  stickyFilters = true,
  filterState = null,
  onFilterChange = null,
  sortState = null,
  onSortChange = null,
  tableStyle = {},
  renderBodyAppend = null,
  renderFooter = null,
}) {
  const visibleColumns = useMemo(
    () => columns.filter((column) => column && column.hidden !== true),
    [columns]
  )

  const defaultWidths = useMemo(
    () => buildDefaultWidths(visibleColumns),
    [visibleColumns]
  )

  const { widths, startResize } = useResizableColumnWidths(defaultWidths)

  const [internalFilters, setInternalFilters] = useState({})
  const [internalSort, setInternalSort] = useState(defaultSort || { key: '', direction: 'asc' })

  const activeFilters = filterState || internalFilters
  const activeSort = sortState || internalSort

  const hasFilters = visibleColumns.some((column) => column.filterable)

  function handleFilterChange(key, value) {
    if (typeof onFilterChange === 'function') {
      onFilterChange(key, value)
      return
    }

    setInternalFilters((current) => ({ ...current, [key]: value }))
  }

  function handleSort(columnKey) {
    const sortDefaults = buildSortDefaults(visibleColumns, defaultSort)
    const next = nextSortState(activeSort, columnKey, sortDefaults)

    if (typeof onSortChange === 'function') {
      onSortChange(next)
      return
    }

    setInternalSort(next)
  }

  const filteredData = useMemo(() => {
    return data.filter((row) => {
      return visibleColumns.every((column) => {
        if (!column.filterable) return true

        const filterValue = normalizeText(activeFilters[column.key])
        if (!filterValue) return true

        const rawValue = typeof column.getFilterValue === 'function'
          ? column.getFilterValue(row)
          : typeof column.getValue === 'function'
            ? column.getValue(row)
            : defaultGetValue(row, column)

        return normalizeText(rawValue).includes(filterValue)
      })
    })
  }, [data, visibleColumns, activeFilters])

  const sortedData = useMemo(() => {
    const sortGetters = Object.fromEntries(
      visibleColumns.map((column) => [
        column.key,
        (row) => {
          if (typeof column.getSortValue === 'function') return column.getSortValue(row)
          if (typeof column.getValue === 'function') return column.getValue(row)
          return defaultGetValue(row, column)
        },
      ])
    )

    return sortItems(filteredData, activeSort, sortGetters)
  }, [filteredData, visibleColumns, activeSort])

  const wrapperClasses = [
    'rz-data-table-wrapper',
    wrapperClassName,
  ].filter(Boolean).join(' ')

  const tableClasses = [
    'rz-data-table',
    stickyHeader ? 'rz-data-table--sticky-header' : '',
    stickyFilters && hasFilters ? 'rz-data-table--sticky-filters' : '',
    tableClassName,
  ].filter(Boolean).join(' ')

  const mergedTableStyle = {
    tableLayout: 'fixed',
    width: buildTableWidth(widths),
    minWidth: buildTableWidth(widths),
    ...tableStyle,
  }

  return (
    <Table
      wrapperClassName={wrapperClasses}
      tableClassName={tableClasses}
      tableStyle={mergedTableStyle}
      dataTestId={dataTestId}
    >
      <colgroup>
        {visibleColumns.map((column) => (
          <col key={column.key} style={{ width: `${widths[column.key] || column.width || 120}px` }} />
        ))}
      </colgroup>

      <thead>
        <tr className="rz-table-header">
          {visibleColumns.map((column) => (
            <ResizableHeaderCell
              key={column.key}
              columnKey={column.key}
              widths={widths}
              onStartResize={startResize}
              className={column.align === 'right' ? 'rz-num' : column.className || ''}
              sortable={Boolean(column.sortable)}
              isSorted={activeSort?.key === column.key}
              sortDirection={activeSort?.direction || column.defaultDirection || 'asc'}
              onSort={column.sortable ? handleSort : null}
              style={column.headerStyle || {}}
            >
              {column.header ?? column.label ?? column.key}
            </ResizableHeaderCell>
          ))}
        </tr>

        {stickyFilters && hasFilters ? (
          <tr className="rz-table-filters">
            {visibleColumns.map((column) => (
              <th key={column.key} className={column.align === 'right' ? 'rz-num' : column.className || ''}>
                {column.filterable ? (
                  <input
                    className="rz-input rz-inline-input"
                    value={activeFilters[column.key] || ''}
                    onChange={(event) => handleFilterChange(column.key, event.target.value)}
                    placeholder={column.filterPlaceholder || 'Filter'}
                    aria-label={column.filterLabel || `Filter op ${column.label || column.key}`}
                  />
                ) : null}
              </th>
            ))}
          </tr>
        ) : null}
      </thead>

      <tbody>
        {sortedData.length === 0 ? (
          <tr>
            <td colSpan={visibleColumns.length}>{emptyMessage}</td>
          </tr>
        ) : renderRow ? (
          sortedData.map((row, index) => renderRow(row, index))
        ) : (
          sortedData.map((row, index) => (
            <tr key={getRowKey(row, index)}>
              {visibleColumns.map((column) => (
                <td key={column.key} className={column.align === 'right' ? 'rz-num' : column.cellClassName || ''}>
                  {typeof column.renderCell === 'function'
                    ? column.renderCell(row, index)
                    : String(defaultGetValue(row, column) ?? '')}
                </td>
              ))}
            </tr>
          ))
        )}
        {typeof renderBodyAppend === 'function' ? renderBodyAppend({ columns: visibleColumns, data: sortedData }) : null}
      </tbody>

      {typeof renderFooter === 'function' ? renderFooter({ columns: visibleColumns, data: sortedData }) : null}
    </Table>
  )
}
