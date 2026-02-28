
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
  const [data] = useState(initialData);
  const [filters, setFilters] = useState({});
  const [selected, setSelected] = useState([]);

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const filteredData = data.filter(row =>
    Object.keys(filters).every(key =>
      !filters[key] || row[key].toString().toLowerCase().includes(filters[key].toLowerCase())
    )
  );

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  return (
    <div className="rz-screen">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div style={{
            background: "#ffffff",
            border: "2px solid #0b5d3b",
            borderRadius: "12px",
            padding: "16px"
          }}>

            <div style={{ marginBottom: "12px", display: "flex", gap: "12px" }}>
              <button className="rz-button-secondary">Verwijderen</button>
              <button className="rz-button-primary">Exporteren</button>
            </div>

            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              background: "#ffffff"
            }}>
              <thead>
                <tr>
                  <th style={{ border: "1px solid #8fd19e", width: "50px" }}>
                    <input
                      type="checkbox"
                      style={{ accentColor: "#0b5d3b" }}
                      checked={selected.length === filteredData.length && filteredData.length > 0}
                      onChange={() =>
                        setSelected(selected.length === filteredData.length ? [] : filteredData.map(d => d.id))
                      }
                    />
                  </th>
                  {["artikel", "aantal", "locatie", "sublocatie"].map(col => (
                    <th key={col} style={{ border: "1px solid #8fd19e", padding: "6px" }}>
                      <div style={{ fontWeight: "600" }}>
                        {col.charAt(0).toUpperCase() + col.slice(1)}
                      </div>
                      <input
                        type="text"
                        value={filters[col] || ""}
                        onChange={(e) => handleFilterChange(col, e.target.value)}
                        placeholder="Filter"
                        style={{ width: "100%", marginTop: "4px" }}
                      />
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody>
                {filteredData.map(row => (
                  <tr key={row.id}>
                    <td style={{ border: "1px solid #8fd19e", textAlign: "center" }}>
                      <input
                        type="checkbox"
                        style={{ accentColor: "#0b5d3b" }}
                        checked={selected.includes(row.id)}
                        onChange={() => toggleSelect(row.id)}
                      />
                    </td>
                    {["artikel", "aantal", "locatie", "sublocatie"].map(field => (
                      <td key={field} style={{
                        border: "1px solid #8fd19e",
                        padding: "8px",
                        background: "#ffffff"
                      }}>
                        {row[field]}
                      </td>
                    ))}
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
