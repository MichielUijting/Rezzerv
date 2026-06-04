import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../../app/AppShell";
import Card from "../../ui/Card";
import Button from "../../ui/Button";
import Input from "../../ui/Input";
import useDismissOnComponentClick from "../../lib/useDismissOnComponentClick.js";
import KassaSmokePanel from "./components/KassaSmokePanel.jsx";

const KASSA_REGRESSION_COUNT = 18;

function getAuthHeaders() {
  const token = localStorage.getItem("rezzerv_token") || "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readJsonOrText(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 1200), non_json_response: true };
  }
}

function chainStatusLabel(status) {
  if (status === "passed") return "Geslaagd";
  if (status === "missing") return "Ontbreekt";
  if (status === "failed") return "Gefaald";
  if (status === "blocked") return "Geblokkeerd";
  return status || "Onbekend";
}

function reportStatusLabel(status) {
  if (status === "passed") return "Geslaagd";
  if (status === "running") return "Bezig";
  if (status === "blocked") return "Geblokkeerd";
  if (status === "failed") return "Gefaald";
  return "Aandacht nodig";
}

function summarizeKassaError(data, fallback) {
  if (!data) return fallback;
  if (Array.isArray(data.blocking_issues) && data.blocking_issues.length) {
    return `Kassa inleesregressie geblokkeerd: ${data.blocking_issues[0]}`;
  }
  if (data.detail) return `Kassa inleesregressie kon niet worden uitgevoerd: ${data.detail}`;
  if (data.message) return `Kassa inleesregressie kon niet worden uitgevoerd: ${data.message}`;
  return fallback;
}

export default function AdminPage() {
  const navigate = useNavigate();

  const [status, setStatus] = useState({ spaces: 0, sublocations: 0, inventory: 0 });
  const [message, setMessage] = useState("");
  const [householdId, setHouseholdId] = useState("demo-household");
  const [isPurgingArchivedReceipts, setIsPurgingArchivedReceipts] = useState(false);
  const [isRunningKassaRegression, setIsRunningKassaRegression] = useState(false);
  const [kassaRegressionJob, setKassaRegressionJob] = useState(null);
  const [kassaRegressionReport, setKassaRegressionReport] = useState(null);

  const [spaceName, setSpaceName] = useState("");
  const [spaceId, setSpaceId] = useState("");
  const [sublocationName, setSublocationName] = useState("");

  const [artikel, setArtikel] = useState("");
  const [aantal, setAantal] = useState("");
  const [inventorySpaceId, setInventorySpaceId] = useState("");
  const [inventorySublocationId, setInventorySublocationId] = useState("");

  useDismissOnComponentClick([() => setMessage("")], Boolean(message));

  async function fetchStatus() {
    try {
      const res = await fetch("/api/dev/status", { headers: getAuthHeaders() });
      const data = await res.json();
      setStatus(data);
    } catch {
      setMessage("Status niet beschikbaar");
    }
  }

  async function fetchKassaRegressionStatus() {
    const res = await fetch("/api/admin/kassa-regression/status", {
      headers: { Accept: "application/json", ...getAuthHeaders() },
    });
    const data = await readJsonOrText(res);
    if (!res.ok) {
      setMessage(summarizeKassaError(data, `Kassa regressiestatus kon niet worden opgehaald. HTTP ${res.status}`));
      return null;
    }
    setKassaRegressionJob(data);
    if (data?.report) setKassaRegressionReport(data.report);
    setIsRunningKassaRegression(data?.status === "running");
    return data;
  }

  useEffect(() => {
    fetchStatus();
    fetchKassaRegressionStatus().catch(() => {});
    const token = localStorage.getItem("rezzerv_token");
    fetch("/api/household", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.id) setHouseholdId(String(data.id));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isRunningKassaRegression) return undefined;
    const timer = window.setInterval(() => {
      fetchKassaRegressionStatus().catch((error) => {
        setMessage(`Kassa regressiestatus kon niet worden opgehaald: ${error?.message || "onbekende fout"}`);
      });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [isRunningKassaRegression]);

  async function postJson(url, payload, successMessage) {
    setMessage("");
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeaders() },
      body: JSON.stringify(payload || {}),
    });
    const data = await res.json();
    if (!res.ok) {
      setMessage(data.detail || "Actie mislukt");
      return null;
    }
    setMessage(successMessage);
    await fetchStatus();
    return data;
  }

  async function handleResetGenerate() {
    setMessage("");
    await fetch("/api/dev/reset-data", { method: "POST", headers: getAuthHeaders() });
    await fetch("/api/dev/generate-demo-data", { method: "POST", headers: getAuthHeaders() });
    navigate("/voorraad", { replace: false });
  }

  async function handlePurgeArchivedReceipts() {
    setMessage("");
    const confirmed = window.confirm("Gearchiveerde kassabonnen definitief verwijderen? Actieve bonnen blijven behouden.");
    if (!confirmed) return;
    setIsPurgingArchivedReceipts(true);
    try {
      const res = await fetch("/api/admin/receipts/purge-archived", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ household_id: householdId }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(data.detail || "Gearchiveerde bonnen definitief verwijderen mislukt");
        return;
      }
      setMessage(`${data.purged_receipt_count || 0} gearchiveerde bon(nen) definitief verwijderd`);
      await fetchStatus();
    } catch {
      setMessage("Gearchiveerde bonnen definitief verwijderen mislukt");
    } finally {
      setIsPurgingArchivedReceipts(false);
    }
  }

  async function handleRunKassaRegression() {
    setMessage("");
    setKassaRegressionReport(null);
    setIsRunningKassaRegression(true);
    try {
      const res = await fetch("/api/admin/kassa-regression/run", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: "{}",
      });
      const data = await readJsonOrText(res);
      if (!res.ok) {
        setKassaRegressionReport(data && typeof data === "object" ? data : null);
        setMessage(summarizeKassaError(data, `Kassa inleesregressie kon niet worden gestart. HTTP ${res.status}`));
        setIsRunningKassaRegression(false);
        return;
      }
      setKassaRegressionJob(data);
      if (data?.report) setKassaRegressionReport(data.report);
      setIsRunningKassaRegression(data?.status === "running");
      setMessage(data?.status === "running" ? "Kassa inleesregressie baseline V8 gestart." : "Kassa inleesregressie bijgewerkt.");
    } catch (error) {
      setIsRunningKassaRegression(false);
      setMessage(`Kassa inleesregressie kon niet worden gestart: ${error?.message || "onbekende frontend/netwerkfout"}`);
    }
  }

  async function handleCreateSpace() {
    const data = await postJson("/api/dev/spaces", { naam: spaceName, household_id: householdId }, "Ruimte toegevoegd");
    if (data?.id) setSpaceId(data.id);
    setSpaceName("");
  }

  async function handleCreateSublocation() {
    await postJson("/api/dev/sublocations", { naam: sublocationName, space_id: spaceId }, "Sublocatie toegevoegd");
    setSublocationName("");
  }

  async function handleCreateInventory() {
    await postJson(
      "/api/dev/inventory",
      { naam: artikel, aantal: Number(aantal), space_id: inventorySpaceId, sublocation_id: inventorySublocationId || null },
      "Voorraadregel toegevoegd"
    );
    setArtikel("");
    setAantal("");
    setInventorySpaceId("");
    setInventorySublocationId("");
  }

  const progressCurrent = Number(kassaRegressionJob?.progress_current || 0);
  const progressTotal = Number(kassaRegressionJob?.progress_total || KASSA_REGRESSION_COUNT);
  const progressPercent = progressTotal > 0 ? Math.round((progressCurrent / progressTotal) * 100) : 0;

  return (
    <AppShell title="Admin / Testdata" showExit={false}>
      <div data-testid="admin-page">
        <Card>
          <div className="rz-admin-grid">
            <div className="rz-admin-panel">
              <h3>Automatische demo data</h3>
              <p className="rz-admin-muted">Genereert ruimtes, sublocaties en voorraadregels voor snelle tests.</p>
              <div className="rz-admin-actions">
                <Button variant="primary" onClick={() => postJson("/api/dev/generate-demo-data", {}, "Demo data gegenereerd")}>Genereer demo data</Button>
                <Button variant="secondary" onClick={handleResetGenerate}>Reset + Demo data</Button>
                <Button variant="secondary" onClick={() => postJson("/api/dev/reset-data", {}, "Demo data verwijderd")}>Reset demo data</Button>
                <Button variant="secondary" onClick={handlePurgeArchivedReceipts} disabled={isPurgingArchivedReceipts}>{isPurgingArchivedReceipts ? "Verwijderen…" : "Gearchiveerde bonnen definitief verwijderen"}</Button>
                <Button variant="secondary" onClick={() => fetch("/api/dev/generate-article-testdata", { method: "POST", headers: getAuthHeaders() }).then(() => navigate("/voorraad", { replace: false }))}>Artikel testdata</Button>
              </div>
            </div>

            <div className="rz-admin-panel">
              <h3>Huidige aantallen</h3>
              <div className="rz-admin-stats">
                <div>Ruimtes: {status.spaces}</div>
                <div>Sublocaties: {status.sublocations}</div>
                <div>Voorraadregels: {status.inventory}</div>
              </div>
            </div>

            <div className="rz-admin-panel" data-testid="kassa-regression-panel">
              <h3>Kassa inleesregressie</h3>
              <p className="rz-admin-muted">Voert baseline V8 uit: 18 vaste testkassabonnen inclusief Picnic. De bonnen worden opnieuw door het parser/inleesproces gehaald en in een tijdelijke aparte testdatabase geschreven. Datum/tijd wordt nooit gevalideerd.</p>
              <div className="rz-admin-actions">
                <Button variant="secondary" onClick={handleRunKassaRegression} disabled={isRunningKassaRegression} data-testid="run-kassa-regression-button">{isRunningKassaRegression ? "Kassa inleesregressie draait…" : "Kassa inleesregressie uitvoeren"}</Button>
              </div>
              {kassaRegressionJob ? (
                <div className="rz-admin-report" data-testid="kassa-regression-progress">
                  <h4 className="rz-admin-status-title">Voortgang kassa inleesregressie</h4>
                  <div className="rz-admin-report-meta">
                    <div>Status: {reportStatusLabel(kassaRegressionJob.status)}</div>
                    <div>Voortgang: bon {progressCurrent} van {progressTotal}</div>
                    <div>Percentage: {progressPercent}%</div>
                    <div>Huidige bon: {kassaRegressionJob.current_case_id || "-"}</div>
                    <div>Bestand: {kassaRegressionJob.current_filename || "-"}</div>
                    <div>Melding: {kassaRegressionJob.message || "-"}</div>
                  </div>
                </div>
              ) : null}
              {kassaRegressionReport ? (
                <div className="rz-admin-report" data-testid="kassa-regression-report">
                  <h4 className="rz-admin-status-title">Laatste kassa inleesregressie</h4>
                  <div className="rz-admin-report-meta">
                    <div>Status: {reportStatusLabel(kassaRegressionReport.status)}</div>
                    <div>Uitgevoerd: {kassaRegressionReport.ran_at || "Onbekend"}</div>
                    <div>Testbron: {kassaRegressionReport.acceptance_basis || "Onbekend"}</div>
                    <div>Vereist: {kassaRegressionReport.summary?.required_receipt_count || KASSA_REGRESSION_COUNT}</div>
                    <div>Getest: {kassaRegressionReport.summary?.tested_receipt_count || 0}</div>
                    <div>Geslaagd: {kassaRegressionReport.summary?.passed_count || 0}</div>
                    <div>Gefaald: {kassaRegressionReport.summary?.failed_count || 0}</div>
                    <div>Geblokkeerd: {kassaRegressionReport.summary?.blocked_count || 0}</div>
                  </div>
                  {(kassaRegressionReport.blocking_issues || []).length ? <div className="rz-admin-report-list">{(kassaRegressionReport.blocking_issues || []).map((issue) => <div key={issue} className="rz-admin-report-row rz-admin-report-row--failed"><div className="rz-admin-report-main"><span>{issue}</span><span>Geblokkeerd</span></div></div>)}</div> : null}
                  <div className="rz-admin-report-list">
                    {(kassaRegressionReport.chains || []).map((item) => (
                      <div key={item.chain} className={`rz-admin-report-row rz-admin-report-row--${item.status === "passed" ? "passed" : "failed"}`}>
                        <div className="rz-admin-report-main"><span>{item.chain}</span><span>{chainStatusLabel(item.status)}</span></div>
                        <div className="rz-admin-report-meta-line">Bonnen: {item.receipt_count} · geslaagd {item.passed_count} · gefaald {item.failed_count}</div>
                        {(item.failures || []).slice(0, 3).map((failure) => <div key={failure.case_id || failure.receipt_id || failure.filename} className="rz-admin-report-meta-line">{failure.case_id || failure.receipt_id || failure.filename}: {failure.error || "onbekende fout"}</div>)}
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <KassaSmokePanel onMessage={setMessage} />

            <div className="rz-admin-panel">
              <h3>Handmatig testdata invoeren</h3>
              <div className="rz-admin-form"><Input placeholder="Naam ruimte" value={spaceName} onChange={(e) => setSpaceName(e.target.value)} /><Button variant="secondary" onClick={handleCreateSpace}>Ruimte toevoegen</Button></div>
              <div className="rz-admin-form"><Input placeholder="Space ID voor sublocatie" value={spaceId} onChange={(e) => setSpaceId(e.target.value)} /><Input placeholder="Naam sublocatie" value={sublocationName} onChange={(e) => setSublocationName(e.target.value)} /><Button variant="secondary" onClick={handleCreateSublocation}>Sublocatie toevoegen</Button></div>
              <div className="rz-admin-form"><Input placeholder="Artikelnaam" value={artikel} onChange={(e) => setArtikel(e.target.value)} /><Input placeholder="Aantal" value={aantal} onChange={(e) => setAantal(e.target.value)} /><Input placeholder="Space ID" value={inventorySpaceId} onChange={(e) => setInventorySpaceId(e.target.value)} /><Input placeholder="Sublocation ID (optioneel)" value={inventorySublocationId} onChange={(e) => setInventorySublocationId(e.target.value)} /><Button variant="secondary" onClick={handleCreateInventory}>Voorraadregel toevoegen</Button></div>
              {message && <div className="rz-admin-message">{message}</div>}
            </div>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
