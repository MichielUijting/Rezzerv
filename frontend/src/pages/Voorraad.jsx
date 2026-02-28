
import React from "react";
import Header from "../ui/Header";

export default function Voorraad() {
  return (
    <div className="rz-screen">
      <Header title="Voorraad" />

      <div className="rz-content">
        <div className="rz-content-inner">

          <div className="rz-matrix">

            <div className="rz-matrix-header">
              <input
                type="text"
                placeholder="Zoek artikel..."
                className="rz-input"
              />
              <button className="rz-button-primary">
                + Artikel
              </button>
            </div>

            <table className="rz-table">
              <thead>
                <tr className="rz-table-header">
                  <th></th>
                  <th>Artikel</th>
                  <th>Aantal</th>
                  <th>Locatie</th>
                  <th>Sublocatie</th>
                  <th>Actie</th>
                </tr>
              </thead>

              <tbody>
                <tr>
                  <td colSpan="6" className="rz-empty-state">
                    Geen voorraaditems beschikbaar.
                  </td>
                </tr>
              </tbody>
            </table>

          </div>

        </div>
      </div>
    </div>
  );
}
