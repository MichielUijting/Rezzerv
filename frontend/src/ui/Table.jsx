
import React from "react";

export default function Table({ columns = [], rows = [], renderRow }) {
  return (
    <div className="rz-table-wrapper">
      <table className="rz-table">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th key={i}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) =>
            renderRow ? renderRow(row, i) : (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j}>{cell}</td>
                ))}
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
