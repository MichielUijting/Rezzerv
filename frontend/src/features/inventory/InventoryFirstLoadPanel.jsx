import { useEffect, useState } from 'react';
import {
  INVENTORY_FIRST_LOAD_EVENT,
  getInventoryFirstLoadHistory,
  inventoryFirstLoadProbeEnabled,
  inventoryFirstLoadReport,
  stopInventoryFirstLoadProbe,
} from './inventoryFirstLoadProbe.js';

function summarizeTrace(trace) {
  const painted = trace.marks.find((mark) => mark.stage === 'first-rows-painted');
  const failed = trace.marks.find((mark) => mark.stage === 'page-error' || mark.stage === 'session-error');
  if (painted) return 'eerste artikelregels na ' + ((painted.timeMs - trace.startedAt) / 1000).toFixed(2) + ' s';
  if (failed) return 'fout tijdens laden (' + failed.stage + ')';
  return 'laden / meting nog niet voltooid';
}

export default function InventoryFirstLoadPanel() {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const update = () => setRevision((current) => current + 1);
    window.addEventListener(INVENTORY_FIRST_LOAD_EVENT, update);
    return () => window.removeEventListener(INVENTORY_FIRST_LOAD_EVENT, update);
  }, []);
  const enabled = inventoryFirstLoadProbeEnabled();
  if (!enabled) return null;
  const recent = getInventoryFirstLoadHistory();
  function download() {
    const blob = new Blob([inventoryFirstLoadReport()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'Inhuis_PR698_Browser_Laadmeting.txt';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section className="rz-card" data-testid="inventory-first-load-diagnostic"
      style={{ margin: '12px 16px', padding: '12px', fontSize: '0.875rem' }}>
      <strong>Diagnose eerste Voorraadlading</strong>
      <p>Alleen tijdmetingen; er worden geen artikel- of accountgegevens vastgelegd.</p>
      {recent.slice(-2).map((trace, index) => (
        <p key={trace.startedAt}>
          {recent.length - Math.min(recent.length, 2) + index + 1}. opening: {summarizeTrace(trace)}
        </p>
      ))}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        <button type="button" onClick={download}>Rapport downloaden</button>
        <button type="button" onClick={stopInventoryFirstLoadProbe}>Diagnose uitzetten</button>
      </div>
    </section>
  );
}
