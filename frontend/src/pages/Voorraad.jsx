import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../ui/Header";
import Button from "../ui/Button";

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}



function normalizeText(value) {
  return String(value || '').trim().toLowerCase()
}

function buildLocalZeroVisibilityKey(row) {
  return String(row?.detailId || row?.id || row?.artikel || '')
}

function mergeVisibleZeroRows(rows = [], localZeroRows = []) {
  const existingKeys = new Set(rows.map((row) => buildLocalZeroVisibilityKey(row)))
  const appended = [...rows]
  localZeroRows.forEach((row) => {
    const key = buildLocalZeroVisibilityKey(row)
    if (!key || existingKeys.has(key)) return
    appended.push({ ...row, aantal: 0, _localZeroVisible: true })
    existingKeys.add(key)
  })
  return appended
}

function buildLocationOptionState(options = []) {
  const locations = []
  const seenLocations = new Set()
  const sublocationsByLocation = new Map()

  options.forEach((option) => {
    const label = String(option?.label || '').trim()
    if (!label) return
    const parts = label.split(' / ')
    const locationName = String(parts[0] || '').trim()
    const sublocationName = String(parts.slice(1).join(' / ') || '').trim()
    if (!locationName) return

    if (!seenLocations.has(locationName)) {
      seenLocations.add(locationName)
      locations.push(locationName)
    }

    if (!sublocationsByLocation.has(locationName)) {
      sublocationsByLocation.set(locationName, [])
    }

    if (sublocationName) {
      const current = sublocationsByLocation.get(locationName)
      if (!current.includes(sublocationName)) current.push(sublocationName)
    }
  })

  locations.sort((a, b) => a.localeCompare(b, 'nl'))
  sublocationsByLocation.forEach((items, key) => {
    items.sort((a, b) => a.localeCompare(b, 'nl'))
    sublocationsByLocation.set(key, items)
  })

  return { locations, sublocationsByLocation }
}

async function fetchLocationOptions() {
  const response = await fetch(`/api/store-location-options?householdId=${encodeURIComponent('demo-household')}&_ts=${Date.now()}`, { cache: 'no-store' })
  if (!response.ok) throw new Error('Locatie-opties konden niet worden geladen')
  const data = await response.json()
  return Array.isArray(data) ? buildLocationOptionState(data) : buildLocationOptionState([])
}

function InlineAutocompleteSelect({
  value,
  options,
  placeholder,
  autoFocus = false,
  emptyMessage = 'Geen resultaten',
  onCommit,
  onCancel,
  onInputChange,
}) {
  const [query, setQuery] = useState(value || '')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const rootRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setQuery(value || '')
  }, [value])

  const filteredOptions = useMemo(() => {
    const needle = normalizeText(query)
    if (!needle) return options
    return options.filter((option) => normalizeText(option).includes(needle))
  }, [options, query])

  useEffect(() => {
    setHighlightedIndex(0)
  }, [query])

  useEffect(() => {
    if (!autoFocus) return
    window.setTimeout(() => {
      inputRef.current?.focus()
      inputRef.current?.select?.()
    }, 0)
  }, [autoFocus])

  const commitSelection = (nextValue) => {
    if (!options.includes(nextValue)) return
    onCommit(nextValue)
  }

  const handleBlur = (event) => {
    const nextTarget = event.relatedTarget
    if (nextTarget && rootRef.current?.contains(nextTarget)) return
    if (query === value) {
      onCancel()
      return
    }
    if (options.includes(query)) {
      onCommit(query)
      return
    }
    onCancel()
  }

  return (
    <div className="rz-inline-autocomplete" ref={rootRef}>
      <input
        ref={inputRef}
        className="rz-input rz-inline-input"
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => {
          const nextValue = e.target.value
          setQuery(nextValue)
          onInputChange?.(nextValue)
        }}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlightedIndex((prev) => Math.min(prev + 1, Math.max(filteredOptions.length - 1, 0)))
            return
          }
          if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlightedIndex((prev) => Math.max(prev - 1, 0))
            return
          }
          if (e.key === 'Enter') {
            e.preventDefault()
            const selected = filteredOptions[highlightedIndex]
            if (selected) commitSelection(selected)
            return
          }
          if (e.key === 'Escape') {
            e.preventDefault()
            onCancel()
          }
        }}
      />
      <div className="rz-inline-autocomplete-menu" role="listbox" aria-label={placeholder}>
        {filteredOptions.length ? filteredOptions.map((option, index) => (
          <button
            key={option}
            type="button"
            className={`rz-inline-autocomplete-option${index === highlightedIndex ? ' is-active' : ''}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => commitSelection(option)}
          >
            {option}
          </button>
        )) : (
          <div className="rz-inline-autocomplete-empty">{emptyMessage}</div>
        )}
      </div>
    </div>
  )
}

function normalizeNumber(value, fallbackValue) {
  if (value === "") return "";
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallbackValue;
}

function mergeInventoryRows(liveRows = []) {
  const grouped = new Map()

  liveRows.forEach((row, index) => {
    const aantal = Number(row?.aantal) || 0
    if (aantal <= 0) return

    const artikel = row?.artikel || ''
    const key = normalizeName(artikel) || `unknown-${index}`
    const existing = grouped.get(key)
    const locatie = row?.locatie || ''
    const sublocatie = row?.sublocatie || ''

    if (!existing) {
      grouped.set(key, {
        id: `agg-${key}`,
        detailId: row.id || `agg-${key}`,
        artikel,
        aantal,
        locatie,
        sublocatie,
        checked: false,
        _rawCount: 1,
        _firstSeenIndex: index,
        _locationValues: new Set([locatie].filter(Boolean)),
        _sublocationValues: new Set([`${locatie}__${sublocatie}`].filter(() => Boolean(sublocatie || locatie))),
      })
      return
    }

    existing.aantal += aantal
    existing._rawCount += 1
    if (locatie) existing._locationValues.add(locatie)
    if (sublocatie || locatie) existing._sublocationValues.add(`${locatie}__${sublocatie}`)
    if (!existing.detailId && row.id) existing.detailId = row.id
  })

  const merged = [...grouped.values()].map((row) => {
    const locations = [...row._locationValues]
    const sublocations = [...row._sublocationValues]
    const isAggregated = row._rawCount > 1
    const hasMultipleLocations = locations.length > 1
    const hasMultipleSublocations = sublocations.length > 1
    return {
      id: row.id,
      detailId: row.detailId,
      artikel: row.artikel,
      aantal: row.aantal,
      locatie: hasMultipleLocations ? 'Meerdere locaties' : (locations[0] || ''),
      sublocatie: hasMultipleSublocations ? 'Meerdere sublocaties' : ((sublocations[0] || '').split('__')[1] || ''),
      checked: false,
      isAggregated,
      canOpenDetails: true,
      canInlineEditArtikel: !isAggregated,
      canInlineEditAantal: !isAggregated,
      canInlineEditLocatie: !isAggregated && !hasMultipleLocations,
      canInlineEditSublocatie: !isAggregated && !hasMultipleSublocations,
      _firstSeenIndex: row._firstSeenIndex,
    }
  })

  return merged.sort((a, b) => (a._firstSeenIndex ?? 0) - (b._firstSeenIndex ?? 0))
}

async function fetchInventoryRows() {
  const response = await fetch(`/api/dev/inventory-preview?_ts=${Date.now()}`, { cache: 'no-store' })
  if (!response.ok) throw new Error("Voorraad kon niet worden geladen")
  const data = await response.json()
  if (!Array.isArray(data?.rows)) return []
  return mergeInventoryRows(data.rows)
}

async function saveInventoryRow(row) {
  const response = await fetch(`/api/dev/inventory/${encodeURIComponent(row.detailId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      naam: row.artikel,
      aantal: Number(row.aantal) || 0,
      space_name: row.locatie || null,
      sublocation_name: row.sublocatie || null,
    }),
  })

  if (!response.ok) {
    let detail = 'Opslaan mislukt'
    try {
      const errorData = await response.json()
      detail = errorData?.detail || detail
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  return response.json()
}

const initialData = [];

const editableColumns = [
  { key: "artikel", label: "Artikel", type: "text", width: "34%" },
  { key: "aantal", label: "Aantal", type: "number", width: "12%" },
  { key: "locatie", label: "Locatie", type: "text", width: "24%" },
  { key: "sublocatie", label: "Sublocatie", type: "text", width: "24%" }
];

function isColumnEditable(row, key) {
  if (key === 'artikel') return Boolean(row?.canInlineEditArtikel)
  if (key === 'aantal') return Boolean(row?.canInlineEditAantal)
  if (key === 'locatie') return Boolean(row?.canInlineEditLocatie)
  if (key === 'sublocatie') return Boolean(row?.canInlineEditSublocatie)
  return false
}

function getColumnLockMessage(row, key) {
  if (row?.isAggregated) return 'Deze rij bundelt meerdere voorraadregels en is daarom niet inline bewerkbaar.'
  if ((key === 'locatie' && !row?.canInlineEditLocatie) || (key === 'sublocatie' && !row?.canInlineEditSublocatie)) {
    return 'Locatievelden met meerdere waarden zijn niet inline bewerkbaar.'
  }
  return 'Niet bewerkbaar'
}

export default function Voorraad() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(initialData);
  const [localZeroRows, setLocalZeroRows] = useState([]);
  const rowsRef = useRef(initialData)
  const draftRowsRef = useRef(new Map())

  useEffect(() => {
    rowsRef.current = rows
  }, [rows])

  const reloadInventoryRows = async () => {
    const loadedRows = await fetchInventoryRows()
    setLocalZeroRows([])
    setRows(loadedRows)
    setLoadError(loadedRows.length ? '' : 'Nog geen live voorraad beschikbaar.')
    return loadedRows
  }
  const [filters, setFilters] = useState({
    artikel: "",
    aantal: "",
    locatie: "",
    sublocatie: ""
  });
  const [editingCell, setEditingCell] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState({});
  const [locationOptions, setLocationOptions] = useState({ locations: [], sublocationsByLocation: new Map() });

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchInventoryRows(), fetchLocationOptions().catch(() => buildLocationOptionState([]))])
      .then(([loadedRows, loadedOptions]) => {
        if (!cancelled) {
          setLocalZeroRows([]);
          setRows(loadedRows);
          setLocationOptions(loadedOptions);
          setLoadError(loadedRows.length ? "" : "Nog geen live voorraad beschikbaar.");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLocalZeroRows([]);
          setRows([]);
          setLoadError("Live voorraad kon niet worden geladen.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);


  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const filteredRows = useMemo(() => {
    const sourceRows = mergeVisibleZeroRows(rows, localZeroRows)
    return sourceRows.filter((row) =>
      editableColumns.every((column) => {
        const filterValue = String(filters[column.key] ?? "").trim().toLowerCase();
        if (!filterValue) return true;
        return String(row[column.key] ?? "").toLowerCase().includes(filterValue);
      })
    );
  }, [rows, localZeroRows, filters]);

  const setRowValue = (rowId, key, value) => {
    setRows((prev) => {
      const nextRows = prev.map((row) =>
        row.id === rowId
          ? { ...row, [key]: key === "aantal" ? normalizeNumber(value, row[key]) : value }
          : row
      )
      const latestRow = nextRows.find((entry) => entry.id === rowId)
      if (latestRow) draftRowsRef.current.set(rowId, { ...latestRow })
      return nextRows
    });
  };

  const toggleRowChecked = (rowId) => {
    setRows((prev) =>
      prev.map((row) => (row.id === rowId ? { ...row, checked: !row.checked } : row))
    );
  };

  const allFilteredChecked =
    filteredRows.length > 0 && filteredRows.every((row) => row.checked);

  const toggleAllFiltered = () => {
    const nextValue = !allFilteredChecked;
    const filteredIds = new Set(filteredRows.map((row) => row.id));

    setRows((prev) =>
      prev.map((row) =>
        filteredIds.has(row.id) ? { ...row, checked: nextValue } : row
      )
    );
  };

  const startEdit = (row, key) => {
    if (!isColumnEditable(row, key)) return;
    setEditingCell({ rowId: row.id, key, originalRow: { ...row } });
  };

  const stopEdit = () => {
    setEditingCell(null);
  };

  const persistEdit = async (row) => {
    if (!editingCell || editingCell.rowId !== row.id) {
      stopEdit();
      return;
    }

    const latestRow = draftRowsRef.current.get(row.id) || rowsRef.current.find((entry) => entry.id === row.id) || row
    const originalRow = editingCell.originalRow || latestRow;
    const changed = ['artikel', 'aantal', 'locatie', 'sublocatie'].some((key) => String(originalRow[key] ?? '') !== String(latestRow[key] ?? ''));

    stopEdit();

    if (!changed) {
      draftRowsRef.current.delete(row.id)
      return;
    }

    setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saving', message: 'Opslaan...' } }));

    try {
      await saveInventoryRow(latestRow)
      if ((Number(latestRow.aantal) || 0) <= 0) {
        setRows((prev) => prev.map((entry) => entry.id === latestRow.id ? { ...entry, aantal: 0, _localZeroVisible: true } : entry))
        setLocalZeroRows((prev) => {
          const key = buildLocalZeroVisibilityKey(latestRow)
          const next = prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== key)
          next.push({ ...latestRow, aantal: 0, _localZeroVisible: true })
          return next
        })
      } else {
        setLocalZeroRows((prev) => prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== buildLocalZeroVisibilityKey(latestRow)))
      }
      const refreshedOptions = await fetchLocationOptions().catch(() => locationOptions)
      setLocationOptions(refreshedOptions)
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saved', message: 'Opgeslagen' } }));
      draftRowsRef.current.delete(row.id)
      window.setTimeout(() => {
        setSaveState((prev) => {
          const next = { ...prev }
          if (next[row.id]?.status === 'saved') delete next[row.id]
          return next
        })
      }, 1600)
    } catch (error) {
      draftRowsRef.current.delete(row.id)
      setLocalZeroRows((prev) => prev.filter((entry) => buildLocalZeroVisibilityKey(entry) !== buildLocalZeroVisibilityKey(row)))
      setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...originalRow } : entry))
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'error', message: error.message || 'Opslaan mislukt' } }));
    }
  }


  const openRowDetails = (row) => {
    if (!row?.canOpenDetails) return
    const detailId = row?.detailId || row?.id
    const artikel = encodeURIComponent(row?.artikel || '')
    navigate(`/voorraad/${detailId}?artikel=${artikel}`)
  }

  const handleRowDoubleClick = (event, row) => {
    const interactiveAncestor = event.target.closest('button, input, select, textarea, a, label')
    if (interactiveAncestor) return
    openRowDetails(row)
  }

  const handleRowKeyDown = (event, row) => {
    if (event.key !== 'Enter' && event.key !== ' ') return
    const interactiveAncestor = event.target.closest('button, input, select, textarea, a, label')
    if (interactiveAncestor) return
    event.preventDefault()
    openRowDetails(row)
  }

  const getEditorOptions = (row, key, typedValue = '') => {
    if (key === 'locatie') return locationOptions.locations
    if (key === 'sublocatie') {
      const activeLocation = row?.locatie || typedValue || ''
      return locationOptions.sublocationsByLocation.get(activeLocation) || []
    }
    return []
  }

  const renderCell = (row, column) => {
    const isEditing =
      editingCell &&
      editingCell.rowId === row.id &&
      editingCell.key === column.key;
    const editable = isColumnEditable(row, column.key)

    if (isEditing) {
      if (column.key === 'locatie' || column.key === 'sublocatie') {
        return (
          <InlineAutocompleteSelect
            value={row[column.key]}
            options={getEditorOptions(row, column.key)}
            placeholder={column.key === 'locatie' ? 'Kies locatie' : 'Kies sublocatie'}
            autoFocus
            emptyMessage="Geen resultaten"
            onInputChange={(nextValue) => {
              if (column.key === 'locatie') {
                setRows((prev) => {
                  const nextRows = prev.map((entry) => entry.id === row.id ? { ...entry, locatie: nextValue, sublocatie: '' } : entry)
                  const latestRow = nextRows.find((entry) => entry.id === row.id)
                  if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                  return nextRows
                })
                return
              }
              setRowValue(row.id, column.key, nextValue)
            }}
            onCommit={(nextValue) => {
              if (column.key === 'locatie') {
                const validSublocations = locationOptions.sublocationsByLocation.get(nextValue) || []
                setRows((prev) => {
                  const nextRows = prev.map((entry) => entry.id === row.id ? {
                    ...entry,
                    locatie: nextValue,
                    sublocatie: validSublocations.includes(entry.sublocatie) ? entry.sublocatie : ''
                  } : entry)
                  const latestRow = nextRows.find((entry) => entry.id === row.id)
                  if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                  return nextRows
                })
                window.setTimeout(() => persistEdit({ ...row, locatie: nextValue, sublocatie: (locationOptions.sublocationsByLocation.get(nextValue) || []).includes(row.sublocatie) ? row.sublocatie : '' }), 0)
                return
              }
              setRows((prev) => {
                const nextRows = prev.map((entry) => entry.id === row.id ? { ...entry, [column.key]: nextValue } : entry)
                const latestRow = nextRows.find((entry) => entry.id === row.id)
                if (latestRow) draftRowsRef.current.set(row.id, { ...latestRow })
                return nextRows
              })
              window.setTimeout(() => persistEdit({ ...row, [column.key]: nextValue }), 0)
            }}
            onCancel={() => {
              setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...editingCell.originalRow } : entry))
              draftRowsRef.current.delete(row.id)
              stopEdit()
            }}
          />
        )
      }

      return (
        <input
          className="rz-input rz-inline-input"
          type={column.type}
          value={row[column.key]}
          autoFocus
          onChange={(e) => setRowValue(row.id, column.key, e.target.value)}
          onBlur={() => persistEdit(row)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              persistEdit(row)
            }
            if (e.key === "Escape") {
              setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...editingCell.originalRow } : entry))
              draftRowsRef.current.delete(row.id)
              stopEdit()
            }
          }}
        />
      );
    }

    if (column.key === "artikel") {
      return (
        <div className="rz-inline-cell rz-inline-label rz-stock-article-cell" title={row?.canOpenDetails ? 'Dubbelklik op de rij voor details' : undefined}>
          <span>{row?.isAggregated ? `${row[column.key]} (samengevoegd)` : row[column.key]}</span>
        </div>
      );
    }

    return (
      <button
        type="button"
        className={
          "rz-inline-cell rz-inline-cell-button" +
          (column.key === "aantal" ? " rz-num" : "") +
          (editable ? "" : " rz-inline-cell-disabled")
        }
        onClick={() => startEdit(row, column.key)}
        title={editable ? 'Klik om te bewerken' : getColumnLockMessage(row, column.key)}
        aria-disabled={!editable}
        disabled={!editable}
      >
        {row[column.key]}
      </button>
    );
  };

  return (
    <div className="rz-screen">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div className="rz-card">
            {loadError && <div style={{ marginBottom: "12px", color: "#b42318", fontWeight: 700 }}>{loadError}</div>}
            <div className="rz-table-wrapper rz-stock-table-wrapper">
              <table className="rz-table rz-stock-table">
                <colgroup>
                  <col style={{ width: "48px" }} />
                  <col style={{ width: "34%" }} />
                  <col style={{ width: "12%" }} />
                  <col style={{ width: "24%" }} />
                  <col style={{ width: "24%" }} />
                </colgroup>

                <thead>
                  <tr className="rz-table-header">
                    <th>
                      <input
                        type="checkbox"
                        checked={allFilteredChecked}
                        onChange={toggleAllFiltered}
                        aria-label="Selecteer alle zichtbare artikelen"
                      />
                    </th>
                    <th>Artikel</th>
                    <th className="rz-num">Aantal</th>
                    <th>Locatie</th>
                    <th>Sublocatie</th>
                  </tr>

                  <tr className="rz-table-filters">
                    <th />
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.artikel}
                        onChange={(e) => handleFilterChange("artikel", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op artikel"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.aantal}
                        onChange={(e) => handleFilterChange("aantal", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op aantal"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.locatie}
                        onChange={(e) => handleFilterChange("locatie", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op locatie"
                      />
                    </th>
                    <th>
                      <input
                        className="rz-input rz-inline-input"
                        value={filters.sublocatie}
                        onChange={(e) => handleFilterChange("sublocatie", e.target.value)}
                        placeholder="Filter"
                        aria-label="Filter op sublocatie"
                      />
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {filteredRows.map((row) => (
                    <tr
                      key={row.id}
                      className={`rz-stock-row-interactive${row.isAggregated ? " rz-stock-row-aggregated" : ""}`}
                      onDoubleClick={(event) => handleRowDoubleClick(event, row)}
                      onKeyDown={(event) => handleRowKeyDown(event, row)}
                      tabIndex={row.canOpenDetails ? 0 : -1}
                      aria-label={row.canOpenDetails ? `Open details van ${row.artikel}${row.isAggregated ? '. Samengevoegde rij, inline aanpassen via details.' : ''}` : undefined}
                      title={row.isAggregated ? 'Samengevoegde rij — pas verdeling aan in details' : (row.canOpenDetails ? 'Dubbelklik voor details' : undefined)}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={row.checked}
                          onChange={() => toggleRowChecked(row.id)}
                          aria-label={`Selecteer ${row.artikel}`}
                        />
                      </td>
                      {editableColumns.map((column) => (
                        <td
                          key={column.key}
                          className={column.key === "aantal" ? "rz-num" : ""}
                        >
                          {renderCell(row, column)}
                          {column.key === 'artikel' && saveState[row.id]?.message ? (
                            <div style={{ marginTop: 4, fontSize: 12, fontWeight: 700, color: saveState[row.id]?.status === 'error' ? '#b42318' : '#067647' }}>
                              {saveState[row.id].message}
                            </div>
                          ) : null}
                        </td>
                      ))}
                    </tr>
                  ))}

                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={5}>{loadError || "Nog geen live voorraad beschikbaar."}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="rz-stock-table-actions">
              <Button type="button" variant="secondary">Exporteren</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
