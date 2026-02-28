
import React from "react";
import Header from "../ui/Header";

export default function Voorraad() {
  return (
    <div className="rz-screen">
      <Header title="Voorraad" />

      <div className="rz-content">
        <div className="rz-content-inner">

          <table className="rz-table">

            <thead>

              <tr>
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
                <th className="rz-align-right">
                  <button className="rz-button-primary">
                    + Artikel
                  </button>
                </th>
              </tr>

              <tr>
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

              <tr>
                <td><input type="checkbox" /></td>
                <td>Rijst</td>
                <td>2</td>
                <td>Keuken</td>
                <td>Kast 1</td>
                <td className="rz-align-right">✏️</td>
              </tr>

              <tr>
                <td><input type="checkbox" /></td>
                <td>Pasta</td>
                <td>3</td>
                <td>Voorraadkast</td>
                <td>Plank 2</td>
                <td className="rz-align-right">✏️</td>
              </tr>

            </tbody>

          </table>

          <div className="rz-mt-md">
            <button className="rz-button-secondary">
              Verwijderen geselecteerd
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
