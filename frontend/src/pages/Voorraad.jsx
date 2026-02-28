
import React from "react";
import Header from "../ui/Header";

export default function Voorraad() {
  return (
    <div className="rz-screen">
      <Header title="Voorraad" />

      <div className="rz-content">
        <div className="rz-content-inner">

          <div className="rz-table-wrapper">

            <table className="rz-table">

              <thead>

                {/* Zoek + actie rij */}
                <tr className="rz-table-toprow">
                  <th></th>
                  <th>
                    <input
                      type="text"
                      placeholder="Zoek artikel..."
                      className="rz-input"
                    />
                  </th>
                  <th></th>
                  <th></th>
                  <th></th>
                  <th style={{ textAlign: "right" }}>
                    <button className="rz-button-primary">+ Artikel</button>
                  </th>
                </tr>

                {/* Filter rij */}
                <tr className="rz-table-filterrow">
                  <th></th>
                  <th>
                    <input type="text" placeholder="Filter" className="rz-input" />
                  </th>
                  <th>
                    <input type="text" placeholder="Filter" className="rz-input" />
                  </th>
                  <th>
                    <input type="text" placeholder="Filter" className="rz-input" />
                  </th>
                  <th>
                    <input type="text" placeholder="Filter" className="rz-input" />
                  </th>
                  <th></th>
                </tr>

                {/* Kolomtitels */}
                <tr className="rz-table-header">
                  <th>
                    <input type="checkbox" />
                  </th>
                  <th>Artikel</th>
                  <th>Aantal</th>
                  <th>Locatie</th>
                  <th>Sublocatie</th>
                  <th>Actie</th>
                </tr>

              </thead>

              <tbody>

                <tr className="rz-table-row">
                  <td><input type="checkbox" /></td>
                  <td>Rijst</td>
                  <td>2</td>
                  <td>Keuken</td>
                  <td>Kast 1</td>
                  <td style={{ textAlign: "right" }}>✏️</td>
                </tr>

                <tr className="rz-table-row">
                  <td><input type="checkbox" /></td>
                  <td>Pasta</td>
                  <td>3</td>
                  <td>Voorraadkast</td>
                  <td>Plank 2</td>
                  <td style={{ textAlign: "right" }}>✏️</td>
                </tr>

              </tbody>

            </table>

            <div className="rz-bulk-actions">
              <button className="rz-button-secondary">
                Verwijderen geselecteerd
              </button>
            </div>

          </div>

        </div>
      </div>
    </div>
  );
}
