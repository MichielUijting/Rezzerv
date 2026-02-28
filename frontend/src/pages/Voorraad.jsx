import React from "react";
import Header from "../ui/Header";

export default function Voorraad() {
  return (
    <div className="rz-page">
      <Header title="Voorraad" />
      <div className="rz-content">
        <table className="rz-table">
          <thead>
            <tr>
              <th><input type="checkbox" /></th>
              <th>Artikel</th>
              <th>Aantal</th>
              <th>Locatie</th>
              <th>Sublocatie</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><input type="checkbox" /></td>
              <td>Voorbeeldartikel</td>
              <td>1</td>
              <td>Keuken</td>
              <td>Kast 1</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
