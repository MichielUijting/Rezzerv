// Opt-in, browser-only diagnostic. No network calls and no user/article identifiers.
export const INVENTORY_FIRST_LOAD_EVENT = 'inhuis-inventory-first-load-diagnostic';
const STORAGE_KEY = 'inhuis-inventory-first-load-diagnostic-enabled';
const HISTORY_KEY = '__inhuisInventoryFirstLoadHistory';

function browserAvailable() {
  return typeof window !== 'undefined' && typeof window.performance !== 'undefined';
}

export function inventoryFirstLoadProbeEnabled() {
  if (!browserAvailable()) return false;
  try {
    if (new URLSearchParams(window.location.search).get('voorraadmeting') === '1') {
      window.sessionStorage.setItem(STORAGE_KEY, '1');
      return true;
    }
    return window.sessionStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return new URLSearchParams(window.location.search).get('voorraadmeting') === '1';
  }
}

export function getInventoryFirstLoadHistory() {
  if (!browserAvailable()) return [];
  return Array.isArray(window[HISTORY_KEY]) ? window[HISTORY_KEY] : [];
}

function announce() {
  window.dispatchEvent(new Event(INVENTORY_FIRST_LOAD_EVENT));
}

export function markInventoryFirstLoad(stage) {
  if (!inventoryFirstLoadProbeEnabled() || window.location.pathname !== '/voorraad') return;
  const now = window.performance.now();
  const history = getInventoryFirstLoadHistory().slice();
  let trace = history[history.length - 1];
  if (stage === 'guard-start') {
    // React StrictMode may run its mount effect twice; do not create
    // duplicate traces for the same mount (<250 ms apart).
    const lastGuard = trace?.marks.find((mark) => mark.stage === 'guard-start');
    if (!trace || !lastGuard || now - lastGuard.timeMs > 250) {
      trace = { startedAt: now, marks: [] };
      history.push(trace);
      if (history.length > 4) history.shift();
    }
  } else if (!trace) {
    return;
  }
  if (!trace.marks.some((mark) => mark.stage === stage)) {
    trace.marks.push({ stage, timeMs: now });
    window[HISTORY_KEY] = history;
    announce();
  }
}

export function inventoryFirstLoadReport() {
  const history = getInventoryFirstLoadHistory();
  const lines = [
    'INHUIS PR #698 - BROWSER LAADMETING (LEZEN, GEEN GEBRUIKERSDATA)',
    'Alle tijden zijn relatief aan start routecontrole, in milliseconden.',
    'Geen persoonlijke gegevens, tokens, voorraadnamen of URLs opgenomen.',
  ];
  history.forEach((trace, index) => {
    lines.push('');
    lines.push('Opening ' + (index + 1) + ':');
    let previous = trace.startedAt;
    trace.marks.forEach((mark) => {
      const total = (mark.timeMs - trace.startedAt).toFixed(1);
      const delta = (mark.timeMs - previous).toFixed(1);
      lines.push(mark.stage + ': +' + total + ' ms (stap ' + delta + ' ms)');
      previous = mark.timeMs;
    });
  });
  if (!history.length) lines.push('Nog geen meetpunten geregistreerd.');
  return lines.join('\n') + '\n';
}

export function stopInventoryFirstLoadProbe() {
  if (!browserAvailable()) return;
  try { window.sessionStorage.removeItem(STORAGE_KEY); } catch {}
  window[HISTORY_KEY] = [];
  announce();
}
