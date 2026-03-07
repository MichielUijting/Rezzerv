import React, { useEffect, useState } from "react";
import AppShell from "../../app/AppShell";
import Card from "../../ui/Card";
import Button from "../../ui/Button";
import Input from "../../ui/Input";
import TestRunPanel from "./components/TestRunPanel";
import TestStatusCard from "./components/TestStatusCard";
import {
  fetchLatestTestReport,
  fetchLatestTestStatus,
  runRegressionTests,
  runSmokeTests,
  submitTestResults,
} from "./services/adminTestingService";
import { runBrowserSmokeTests } from "./lib/browserSmokeRunner";

export default function AdminPage() {

  async function handleResetGenerate() {
    setMessage("");
    await fetch("/api/dev/reset-data",{method:"POST"});
    await fetch("/api/dev/generate-demo-data",{method:"POST"});
    window.location.href="/voorraad";
  }

  const [status, setStatus] = useState({ spaces: 0, sublocations: 0, inventory: 0 });
  const [message, setMessage] = useState("");

  const [spaceName, setSpaceName] = useState("");
  const [spaceId, setSpaceId] = useState("");
  const [sublocationName, setSublocationName] = useState("");

  const [artikel, setArtikel] = useState("");
  const [aantal, setAantal] = useState("");
  const [inventorySpaceId, setInventorySpaceId] = useState("");
  const [inventorySublocationId, setInventorySublocationId] = useState("");

  const [testStatus, setTestStatus] = useState({
    test_type: null,
    status: "idle",
    last_run_at: null,
    passed_count: 0,
    failed_count: 0,
    last_error: null,
  });
  const [testReport, setTestReport] = useState(null);
  const [testMessage, setTestMessage] = useState("");
  const [showReport, setShowReport] = useState(false);

  async function fetchStatus() {
    try {
      const res = await fetch("/api/dev/status");
      const data = await res.json();
      setStatus(data);
    } catch {
      setMessage("Status niet beschikbaar");
    }
  }

  async function refreshTestStatus() {
    try {
      const statusData = await fetchLatestTestStatus();
      setTestStatus(statusData);
    } catch {
      setTestMessage("Teststatus niet beschikbaar");
    }
  }

  useEffect(() => {
    fetchStatus();
    refreshTestStatus();
  }, []);

  useEffect(() => {
    if (testStatus.status !== "running") {
      return undefined;
    }

    const timer = window.setInterval(() => {
      refreshTestStatus();
    }, 1000);

    return () => window.clearInterval(timer);
  }, [testStatus.status]);

  async function postJson(url, payload, successMessage) {
    setMessage("");
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    const data = await res.json();
    if (!res.ok) {
      setMessage(data.detail || "Actie mislukt");
      return;
    }
    setMessage(successMessage);
    await fetchStatus();
    return data;
  }

  async function handleGenerateDemo() {
    await postJson("/api/dev/generate-demo-data", {}, "Demo data gegenereerd");
  }

  async function handleReset() {
    await postJson("/api/dev/reset-data", {}, "Demo data verwijderd");
  }

  async function handleCreateSpace() {
    const data = await postJson(
      "/api/dev/spaces",
      { naam: spaceName },
      "Ruimte toegevoegd"
    );
    if (data?.id) {
      setSpaceId(data.id);
    }
    setSpaceName("");
  }

  async function handleCreateSublocation() {
    await postJson(
      "/api/dev/sublocations",
      { naam: sublocationName, space_id: spaceId },
      "Sublocatie toegevoegd"
    );
    setSublocationName("");
  }

  async function handleCreateInventory() {
    await postJson(
      "/api/dev/inventory",
      {
        naam: artikel,
        aantal: Number(aantal),
        space_id: inventorySpaceId,
        sublocation_id: inventorySublocationId || null
      },
      "Voorraadregel toegevoegd"
    );
    setArtikel("");
    setAantal("");
    setInventorySpaceId("");
    setInventorySublocationId("");
  }

  async function handleRunSmoke() {
    setTestMessage("");
    setShowReport(false);
    try {
      const result = await runSmokeTests();
      setTestStatus((current) => ({ ...current, ...result }));
      if (!result.started) {
        setTestMessage("Er loopt al een test");
        await refreshTestStatus();
        return;
      }

      setTestMessage("Smoke test gestart");
      const results = await runBrowserSmokeTests();
      await submitTestResults('smoke', results);
      await refreshTestStatus();
      const latestReport = await fetchLatestTestReport();
      setTestReport(latestReport);
      setShowReport(true);
      setTestMessage('Smoke test afgerond');
    } catch (error) {
      try {
        await submitTestResults('smoke', [{ name: 'Smoke test runner', status: 'failed', error: error.message || 'Smoke test kon niet worden uitgevoerd' }]);
        await refreshTestStatus();
      } catch {
        // negeer secundaire fout
      }
      setTestMessage(error.message || "Smoke test kon niet worden gestart");
    }
  }

  async function handleRunRegression() {
    setTestMessage("");
    setShowReport(false);
    try {
      const result = await runRegressionTests();
      setTestStatus((current) => ({ ...current, ...result }));
      setTestMessage(result.started ? "Volledige regressietest gestart" : "Er loopt al een test");
      await refreshTestStatus();
    } catch (error) {
      setTestMessage(error.message || "Regressietest kon niet worden gestart");
    }
  }

  async function handleViewReport() {
    setTestMessage("");
    try {
      const report = await fetchLatestTestReport();
      setTestReport(report);
      setShowReport(true);
    } catch (error) {
      setTestMessage(error.message || "Testrapport niet beschikbaar");
    }
  }

  return (
    <AppShell title="Admin / Testdata" showExit={false}>
      <Card>
        <div className="rz-admin-grid">
          <div className="rz-admin-panel">
            <h3>Automatische demo data</h3>
            <p className="rz-admin-muted">
              Genereert ruimtes, sublocaties en voorraadregels voor snelle tests.
            </p>
            <div className="rz-admin-actions">
              <Button variant="primary" onClick={handleGenerateDemo}>Genereer demo data</Button>
              <Button variant="secondary" onClick={handleResetGenerate}>Reset + Demo data</Button>
              <Button variant="secondary" onClick={handleReset}>Reset demo data</Button>
              <Button variant="secondary" onClick={async ()=>{await fetch("/api/dev/generate-article-testdata",{method:"POST"});window.location.href="/voorraad";}}>Artikel testdata</Button>
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

          <div className="rz-admin-panel">
            <h3>Testen</h3>
            <p className="rz-admin-muted">
              Start hier een smoke test of een volledige regressietest en bekijk de laatste status.
            </p>
            <TestRunPanel
              isRunning={testStatus.status === "running"}
              onRunSmoke={handleRunSmoke}
              onRunRegression={handleRunRegression}
              onViewReport={handleViewReport}
            />
            {testMessage ? <div className="rz-admin-message">{testMessage}</div> : null}
            <TestStatusCard status={testStatus} />
            {showReport && testReport ? (
              <div className="rz-admin-report">
                <h4 className="rz-admin-status-title">Laatste testrapport</h4>
                <div className="rz-admin-report-meta">
                  <div>Testtype: {testReport.test_type || "Onbekend"}</div>
                  <div>Laatste run: {testReport.last_run_at ? new Date(testReport.last_run_at).toLocaleString("nl-NL") : "Nog geen rapport"}</div>
                </div>
                <div className="rz-admin-report-list">
                  {testReport.results?.length ? testReport.results.map((result) => (
                    <div key={result.name} className={`rz-admin-report-row rz-admin-report-row--${result.status}`}>
                      <span>{result.name}</span>
                      <span>{result.status === "passed" ? "Geslaagd" : "Gefaald"}</span>
                    </div>
                  )) : <div className="rz-admin-muted">Nog geen rapport beschikbaar</div>}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rz-admin-panel">
            <h3>Handmatig testdata invoeren</h3>

            <div className="rz-admin-form">
              <Input placeholder="Naam ruimte" value={spaceName} onChange={(e) => setSpaceName(e.target.value)} />
              <Button variant="secondary" onClick={handleCreateSpace}>Ruimte toevoegen</Button>
            </div>

            <div className="rz-admin-form">
              <Input placeholder="Space ID voor sublocatie" value={spaceId} onChange={(e) => setSpaceId(e.target.value)} />
              <Input placeholder="Naam sublocatie" value={sublocationName} onChange={(e) => setSublocationName(e.target.value)} />
              <Button variant="secondary" onClick={handleCreateSublocation}>Sublocatie toevoegen</Button>
            </div>

            <div className="rz-admin-form">
              <Input placeholder="Artikelnaam" value={artikel} onChange={(e) => setArtikel(e.target.value)} />
              <Input placeholder="Aantal" value={aantal} onChange={(e) => setAantal(e.target.value)} />
              <Input placeholder="Space ID" value={inventorySpaceId} onChange={(e) => setInventorySpaceId(e.target.value)} />
              <Input placeholder="Sublocation ID (optioneel)" value={inventorySublocationId} onChange={(e) => setInventorySublocationId(e.target.value)} />
              <Button variant="secondary" onClick={handleCreateInventory}>Voorraadregel toevoegen</Button>
            </div>

            {message && <div className="rz-admin-message">{message}</div>}
          </div>
        </div>
      </Card>
    </AppShell>
  );
}
