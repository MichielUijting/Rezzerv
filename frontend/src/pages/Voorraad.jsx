
import React, { useState } from "react";
import Header from "../ui/Header";

const initialData = [
  { id: 1, artikel: "Rijst", aantal: 2, locatie: "Keuken", sublocatie: "Kast 1" },
  { id: 2, artikel: "Pasta", aantal: 3, locatie: "Voorraadkast", sublocatie: "Plank 2" },
  { id: 3, artikel: "Tomaten", aantal: 6, locatie: "Keuken", sublocatie: "Koelkast" },
  { id: 4, artikel: "Koffie", aantal: 1, locatie: "Keuken", sublocatie: "Kast 2" },
  { id: 5, artikel: "Shampoo", aantal: 4, locatie: "Badkamer", sublocatie: "Kast" }
];

export default function Voorraad() {
  const [data, setData] = useState(initialData);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");
  const [selected, setSelected] = useState([]);
  const [editingCell, setEditingCell] = useState(null);

  const toggleSort = (key) => {
    if (sortKey === key) {
      if (sortDir === "asc") setSortDir("desc");
      else { setSortKey(null); setSortDir("asc"); }
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortedData = [...data].sort((a, b) => {
    if (!sortKey) return 0;
    if (a[sortKey] < b[sortKey]) return sortDir === "asc" ? -1 : 1;
    if (a[sortKey] > b[sortKey]) return sortDir === "asc" ? 1 : -1;
    return 0;
  });

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const handleEdit = (id, field, value) => {
    setData(prev =>
      prev.map(row =>
        row.id === id ? { ...row, [field]: field === "aantal" ? parseInt(value || 0) : value } : row
      )
    );
  };

  return (
    <div className="rz-screen">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div className="rz-matrix">
            <table className="rz-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr className="rz-table-header">
                  <th style={{ width: "50px" }}>
                    <input
                      type="checkbox"
                      checked={selected.length === data.length}
                      onChange={() =>
                        setSelected(selected.length === data.length ? [] : data.map(d => d.id))
                      }
                    />
                  </th>
                  {["artikel", "aantal", "locatie", "sublocatie"].map(col => (
                    <th key={col} onClick={() => toggleSort(col)} style={{ cursor: "pointer", borderLeft: "1px solid #ddd" }}>
                      {col.charAt(0).toUpperCase() + col.slice(1)}
                      {sortKey === col && (sortDir === "asc" ? " ↑" : " ↓")}
                    </th>
                  ))}
                  <th style={{ width: "60px", borderLeft: "1px solid #ddd" }}>Actie</th>
                </tr>
              </thead>
              <tbody>
                {sortedData.map(row => (
                  <tr key={row.id} style={{ borderTop: "1px solid #eee" }}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selected.includes(row.id)}
                        onChange={() => toggleSelect(row.id)}
                      />
                    </td>
                    {["artikel", "aantal", "locatie", "sublocatie"].map(field => (
                      <td
                        key={field}
                        style={{ borderLeft: "1px solid #eee", padding: "6px" }}
                        onClick={() => setEditingCell({ id: row.id, field })}
                      >
                        {editingCell &&
                        editingCell.id === row.id &&
                        editingCell.field === field ? (
                          <input
                            type={field === "aantal" ? "number" : "text"}
                            value={row[field]}
                            autoFocus
                            onBlur={(e) => {
                              handleEdit(row.id, field, e.target.value);
                              setEditingCell(null);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                handleEdit(row.id, field, e.target.value);
                                setEditingCell(null);
                              }
                              if (e.key === "Escape") setEditingCell(null);
                            }}
                          />
                        ) : (
                          row[field]
                        )}
                      </td>
                    ))}
                    <td style={{ textAlign: "center" }}>✏</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
