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
          <div className="rz-card-elevated">

            <table className="rz-table">
              
              <thead>
                <tr>
                  <th className="rz-align-left">
                    <input
                      type="checkbox"
                      style={{ accentColor: "var(--color-brand-primary)" }}
                      checked={selected.length === filteredData.length && filteredData.length > 0}
                      onChange={() =>
                        setSelected(selected.length === filteredData.length ? [] : filteredData.map(d => d.id))
                      }
                    />
                  </th>
                  <th className="rz-align-left">Artikel</th>
                  <th className="rz-align-right">Aantal</th>
                  <th className="rz-align-left">Locatie</th>
                  <th className="rz-align-left">Sublocatie</th>
                </tr>

                <tr className="rz-table-filters">
                  <th></th>
                  <th className="rz-align-left">
                    <input
                      type="text"
                      className="rz-input"
                      value={filters.artikel || ""}
                      onChange={(e) => handleFilterChange("artikel", e.target.value)}
                      placeholder="Filter"
                    />
                  </th>
                  <th className="rz-align-right">
                    <input
                      type="text"
                      className="rz-input"
                      value={filters.aantal || ""}
                      onChange={(e) => handleFilterChange("aantal", e.target.value)}
                      placeholder="Filter"
                    />
                  </th>
                  <th className="rz-align-left">
                    <input
                      type="text"
                      className="rz-input"
                      value={filters.locatie || ""}
                      onChange={(e) => handleFilterChange("locatie", e.target.value)}
                      placeholder="Filter"
                    />
                  </th>
                  <th className="rz-align-left">
                    <input
                      type="text"
                      className="rz-input"
                      value={filters.sublocatie || ""}
                      onChange={(e) => handleFilterChange("sublocatie", e.target.value)}
                      placeholder="Filter"
                    />
                  </th>
                </tr>
              </thead>
    

              
              <tbody>
                {filteredData.length === 0 && (
                  <tr>
                    <td colSpan="5" style={{ textAlign: "center", padding: "24px", opacity: 0.6 }}>
                      Geen artikelen gevonden.
                    </td>
                  </tr>
                )}

                {filteredData.map(row => (
                  <tr key={row.id}>
                    <td className="rz-align-left">
                      <input
                        type="checkbox"
                        style={{ accentColor: "var(--color-brand-primary)" }}
                        checked={selected.includes(row.id)}
                        onChange={() => toggleSelect(row.id)}
                      />
                    </td>
                    <td className="rz-align-left">{row.artikel}</td>
                    <td className="rz-align-right">{row.aantal}</td>
                    <td className="rz-align-left">{row.locatie}</td>
                    <td className="rz-align-left">{row.sublocatie}</td>
                  </tr>
                ))}
              </tbody>
    
            </table>

            <div style={{ marginTop: "18px", display: "flex", gap: "12px" }}>
              <button className="rz-button-primary" disabled={selected.length === 0}>Verwijderen</button>
              <button className="rz-button-primary" disabled={selected.length === 0}>Exporteren</button>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}