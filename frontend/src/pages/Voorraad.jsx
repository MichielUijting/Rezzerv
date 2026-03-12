import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Header from "../ui/Header";

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}

function normalizeNumber(value, fallbackValue) {
  if (value === "") return "";
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallbackValue;
}

function mergeInventoryRows(liveRows = []) {
  const grouped = new Map()

  liveRows.forEach((row, index) => {
    const artikel = row?.artikel || ''
    const key = normalizeName(artikel) || `unknown-${index}`
    const existing = grouped.get(key)
    const aantal = Number(row?.aantal) || 0
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
      canEditArtikel: !isAggregated,
      canEditAantal: !isAggregated,
      canEditLocatie: !isAggregated && !hasMultipleLocations,
      canEditSublocatie: !isAggregated && !hasMultipleSublocations,
    }
  })

  return merged.sort((a, b) => String(a.artikel || '').localeCompare(String(b.artikel || ''), 'nl'))
}

async function fetchInventoryRows() {
  const response = await fetch("/api/dev/inventory-preview")
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
  if (key === 'artikel') return Boolean(row?.canEditArtikel)
  if (key === 'aantal') return Boolean(row?.canEditAantal)
  if (key === 'locatie') return Boolean(row?.canEditLocatie)
  if (key === 'sublocatie') return Boolean(row?.canEditSublocatie)
  return false
}

function getColumnLockMessage(row, key) {
  if (row?.isAggregated) return 'Deze rij bundelt meerdere voorraadregels en is daarom niet inline bewerkbaar.'
  if ((key === 'locatie' && !row?.canEditLocatie) || (key === 'sublocatie' && !row?.canEditSublocatie)) {
    return 'Locatievelden met meerdere waarden zijn niet inline bewerkbaar.'
  }
  return 'Niet bewerkbaar'
}

export default function Voorraad() {
  const [rows, setRows] = useState(initialData);

  const reloadInventoryRows = async () => {
    const loadedRows = await fetchInventoryRows()
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

  useEffect(() => {
    let cancelled = false;
    fetchInventoryRows()
      .then((loadedRows) => {
        if (!cancelled) {
          setRows(loadedRows);
          setLoadError(loadedRows.length ? "" : "Nog geen live voorraad beschikbaar.");
        }
      })
      .catch(() => {
        if (!cancelled) {
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
    return rows.filter((row) =>
      editableColumns.every((column) => {
        const filterValue = String(filters[column.key] ?? "").trim().toLowerCase();
        if (!filterValue) return true;
        return String(row[column.key] ?? "").toLowerCase().includes(filterValue);
      })
    );
  }, [rows, filters]);

  const setRowValue = (rowId, key, value) => {
    setRows((prev) =>
      prev.map((row) =>
        row.id === rowId
          ? { ...row, [key]: key === "aantal" ? normalizeNumber(value, row[key]) : value }
          : row
      )
    );
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

    const originalRow = editingCell.originalRow || row;
    const changed = ['artikel', 'aantal', 'locatie', 'sublocatie'].some((key) => String(originalRow[key] ?? '') !== String(row[key] ?? ''));

    stopEdit();

    if (!changed) return;

    setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saving', message: 'Opslaan...' } }));

    try {
      await saveInventoryRow(row)
      await reloadInventoryRows()
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'saved', message: 'Opgeslagen' } }));
      window.setTimeout(() => {
        setSaveState((prev) => {
          const next = { ...prev }
          if (next[row.id]?.status === 'saved') delete next[row.id]
          return next
        })
      }, 1600)
    } catch (error) {
      setRows((prev) => prev.map((entry) => entry.id === row.id ? { ...entry, ...originalRow } : entry))
      setSaveState((prev) => ({ ...prev, [row.id]: { status: 'error', message: error.message || 'Opslaan mislukt' } }));
    }
  }

  const renderCell = (row, column) => {
    const isEditing =
      editingCell &&
      editingCell.rowId === row.id &&
      editingCell.key === column.key;
    const editable = isColumnEditable(row, column.key)

    if (isEditing) {
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
              stopEdit()
            }
          }}
        />
      );
    }

    if (column.key === "artikel") {
      const detailId = row?.detailId || row?.id
      const artikel = encodeURIComponent(row?.artikel || '')
      const detailHref = `/voorraad/${detailId}?artikel=${artikel}`

      return (
        <Link
          className="rz-inline-cell rz-inline-link"
          to={detailHref}
          title="Open details"
          aria-label={`Open details van ${row.artikel || 'artikel'}`}
        >
          {row[column.key]}
        </Link>
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
                    <tr key={row.id} className="rz-stock-row-interactive">
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
          </div>
        </div>
      </div>
    </div>
  );
}
