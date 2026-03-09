import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../ui/Header";
import demoData from "../demo-articles.json";

function buildRowsFromArticles(articles) {
  return articles.map((article) => {
    const firstLocation = article.locations?.[0] || {};
    const totalQuantity = (article.locations || []).reduce(
      (sum, entry) => sum + (Number(entry.aantal) || 0),
      0
    );

    return {
      id: article.id,
      artikel: article.name,
      aantal: totalQuantity,
      locatie: firstLocation.locatie || "",
      sublocatie: firstLocation.sublocatie || "",
      checked: false,
    };
  });
}

const initialData = buildRowsFromArticles(demoData.articles || []);

function normalizeName(value) {
  return String(value || '').trim().toLowerCase()
}

function mergeInventoryRows(liveRows = []) {
  const demoByName = new Map(initialData.map((row) => [normalizeName(row.artikel), row]))
  const merged = []
  const seen = new Set()

  liveRows.forEach((row, index) => {
    const key = normalizeName(row?.artikel)
    const demoRow = demoByName.get(key)
    merged.push({
      ...row,
      id: row.id || `${key}-${index}`,
      detailId: demoRow?.id || row.id,
      artikel: row.artikel || demoRow?.artikel || '',
      aantal: row.aantal ?? demoRow?.aantal ?? '',
      locatie: row.locatie ?? demoRow?.locatie ?? '',
      sublocatie: row.sublocatie ?? demoRow?.sublocatie ?? '',
      checked: false,
    })
    seen.add(key)
  })

  initialData.forEach((row) => {
    const key = normalizeName(row.artikel)
    if (seen.has(key)) return
    merged.push({ ...row, detailId: row.id, checked: false })
  })

  return merged.sort((a, b) => String(a.artikel || '').localeCompare(String(b.artikel || ''), 'nl'))
}

async function fetchInventoryRows() {
  const response = await fetch("/api/dev/inventory-preview")
  if (!response.ok) throw new Error("Voorraad kon niet worden geladen")
  const data = await response.json()
  if (!Array.isArray(data?.rows)) return initialData
  return mergeInventoryRows(data.rows)
}

const editableColumns = [
  { key: "artikel", label: "Artikel", type: "text", width: "34%" },
  { key: "aantal", label: "Aantal", type: "number", width: "12%" },
  { key: "locatie", label: "Locatie", type: "text", width: "24%" },
  { key: "sublocatie", label: "Sublocatie", type: "text", width: "24%" }
];

export default function Voorraad() {
  const navigate = useNavigate();
  const [rows, setRows] = useState(initialData);
  const [filters, setFilters] = useState({
    artikel: "",
    aantal: "",
    locatie: "",
    sublocatie: ""
  });
  const [editingCell, setEditingCell] = useState(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchInventoryRows()
      .then((loadedRows) => {
        if (!cancelled && loadedRows.length) setRows(loadedRows);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Live voorraad kon niet worden geladen. Demo-overzicht wordt getoond.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openArticle = (detailId) => {
    navigate(`/voorraad/${detailId}`);
  };

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

  const startEdit = (rowId, key) => {
    setEditingCell({ rowId, key });
  };

  const stopEdit = () => {
    setEditingCell(null);
  };

  const renderCell = (row, column) => {
    const isEditing =
      editingCell &&
      editingCell.rowId === row.id &&
      editingCell.key === column.key;

    if (isEditing) {
      return (
        <input
          className="rz-input rz-inline-input"
          type={column.type}
          value={row[column.key]}
          autoFocus
          onChange={(e) => setRowValue(row.id, column.key, e.target.value)}
          onBlur={stopEdit}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === "Escape") {
              stopEdit();
            }
          }}
        />
      );
    }

    return (
      <div
        className={"rz-inline-cell" + (column.key === "aantal" ? " rz-num" : "")}
        onClick={() => startEdit(row.id, column.key)}
        title="Klik om te bewerken, dubbelklik voor details"
      >
        {row[column.key]}
      </div>
    );
  };

  return (
    <div className="rz-screen">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div className="rz-card">
            {loadError && <div style={{ marginBottom: "12px", color: "#b42318", fontWeight: 700 }}>{loadError}</div>}
            <div className="rz-table-wrapper">
              <table className="rz-table">
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
                    <tr key={row.id} onDoubleClick={() => openArticle(row.detailId || row.id)}>
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
                        </td>
                      ))}
                    </tr>
                  ))}

                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={5}>Geen artikelen gevonden.</td>
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

function normalizeNumber(value, fallbackValue) {
  if (value === "") return "";
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : fallbackValue;
}
