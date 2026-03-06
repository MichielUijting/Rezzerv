import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../ui/Header";

const initialData = [
  { id: 1, artikel: "Rijst", aantal: 2, locatie: "Keuken", sublocatie: "Kast 1", checked: false },
  { id: 2, artikel: "Pasta", aantal: 3, locatie: "Voorraadkast", sublocatie: "Plank 2", checked: false },
  { id: 3, artikel: "Tomaten", aantal: 6, locatie: "Keuken", sublocatie: "Koelkast", checked: false },
  { id: 4, artikel: "Koffie", aantal: 1, locatie: "Keuken", sublocatie: "Kast 2", checked: false },
  { id: 5, artikel: "Shampoo", aantal: 4, locatie: "Badkamer", sublocatie: "Kast", checked: false }
];

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

  const openArticle = (id) => {
    navigate(`/voorraad/${id}`);
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
                    <tr key={row.id} onDoubleClick={() => openArticle(row.id)}>
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
