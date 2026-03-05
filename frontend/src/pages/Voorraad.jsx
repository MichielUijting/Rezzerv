
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from "../ui/Header";

const initialData = [
  { id: 1, artikel: "Rijst", aantal: 2, locatie: "Keuken", sublocatie: "Kast 1" },
  { id: 2, artikel: "Pasta", aantal: 3, locatie: "Voorraadkast", sublocatie: "Plank 2" },
  { id: 3, artikel: "Tomaten", aantal: 6, locatie: "Keuken", sublocatie: "Koelkast" },
  { id: 4, artikel: "Koffie", aantal: 1, locatie: "Keuken", sublocatie: "Kast 2" },
  { id: 5, artikel: "Shampoo", aantal: 4, locatie: "Badkamer", sublocatie: "Kast" }
];

export default function Voorraad() {

  const navigate = useNavigate();
  const [data] = useState(initialData);

  const openArticle = (id) => {
    navigate(`/voorraad/${id}`);
  };

  return (
    <div className="rz-screen">
      <Header title="Voorraad" />
      <div className="rz-content">
        <div className="rz-content-inner">
          <div className="rz-card">

            <table className="rz-table">
              <thead>
                <tr>
                  <th>Artikel</th>
                  <th>Aantal</th>
                  <th>Locatie</th>
                  <th>Sublocatie</th>
                </tr>
              </thead>
              <tbody>
                {data.map(row => (
                  <tr key={row.id} onDoubleClick={() => openArticle(row.id)}>
                    <td>{row.artikel}</td>
                    <td>{row.aantal}</td>
                    <td>{row.locatie}</td>
                    <td>{row.sublocatie}</td>
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
