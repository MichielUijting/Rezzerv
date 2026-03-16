import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../../app/AppShell";
import Card from "../../ui/Card";
import Button from "../../ui/Button";
import Input from "../../ui/Input";
import TestRunPanel from "./components/TestRunPanel";
import TestStatusCard from "./components/TestStatusCard";
import {
  fetchLatestTestReport,
  fetchLatestTestStatus,
  runLayer1Tests,
  runRegressionTests,
  runSmokeTests,
  submitTestResults,
} from "./services/adminTestingService";
import { runBrowserSmokeTests } from "./lib/browserSmokeRunner";
import { runLayer1RegressionTests } from "./lib/layer1RegressionRunner";
import { runBrowserRegressionTests } from "./lib/browserRegressionRunner";

export default function AdminPage() {
  const navigate = useNavigate();

  async function handleResetGenerate() {
    setMessage("");
    await fetch("/api/dev/reset-data",{method:"POST"});
    await fetch("/api/dev/generate-demo-data",{method:"POST"});
    navigate("/voorraad", { replace: false });
  }

  const [status, setStatus] = useState({ spaces: 0, sublocations: 0, inventory: 0 });
  const [message, setMessage] = useState("");
  const [householdId, setHouseholdId] = useState("demo-household");

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
  const [diagnostics, setDiagnostics] = useState({ location: null, process: null });
  const [regressionProgress, setRegressionProgress] = useState({ status: 'idle', activeScenario: null, activeStep: null, completedScenario: null, lastError: null, updatedAt: null });
  const [diagnosticMessage, setDiagnosticMessage] = useState("");
  const [isRunningLocationDiagnostic, setIsRunningLocationDiagnostic] = useState(false);
  const [isRunningProcessDiagnostic, setIsRunningProcessDiagnostic] = useState(false);

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
    const token = localStorage.getItem("rezzerv_token");
    fetch("/api/household", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.id) setHouseholdId(String(data.id))
      })
      .catch(() => {});
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

  useEffect(() => {
    function syncRegressionProgress() {
      try {
        const raw = localStorage.getItem('rezzerv_regression_progress')
        if (!raw) return
        const parsed = JSON.parse(raw)
        setRegressionProgress((current) => ({ ...current, ...(parsed || {}) }))
      } catch {}
    }

    syncRegressionProgress()
    const timer = window.setInterval(syncRegressionProgress, 500)
    return () => window.clearInterval(timer)
  }, []);

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

  async function handleRunLocationDiagnostic() {
    setDiagnosticMessage("");
    setIsRunningLocationDiagnostic(true);
    try {
      const res = await fetch('/api/dev/diagnostics/store-location-options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ household_id: householdId }),
      });
      const data = await res.json();
      setDiagnostics((current) => ({ ...current, location: data }));
      setDiagnosticMessage(data.visible_in_store_location_options
        ? 'Dropdown-diagnose geslaagd: testlocatie zit in store-location-options.'
        : 'Dropdown-diagnose gefaald: testlocatie ontbreekt in store-location-options.');
    } catch {
      setDiagnosticMessage('Dropdown-diagnose kon niet worden uitgevoerd');
    } finally {
      setIsRunningLocationDiagnostic(false);
    }
  }

  async function handleRunProcessDiagnostic() {
    setDiagnosticMessage("");
    setIsRunningProcessDiagnostic(true);
    try {
      const res = await fetch(`/api/dev/diagnostics/store-process-validation?householdId=${encodeURIComponent(householdId)}`);
      const data = await res.json();
      setDiagnostics((current) => ({ ...current, process: data }));
      if (!data.has_batch) {
        setDiagnosticMessage('Geen kassabonbatch beschikbaar voor validatiediagnose.');
      } else if ((data.missing_valid_location_count || 0) > 0 || (data.missing_article_count || 0) > 0) {
        setDiagnosticMessage(`Diagnose afgerond: ${data.missing_valid_location_count || 0} regel(s) zonder geldige locatie, ${data.missing_article_count || 0} regel(s) zonder geldig artikel.`);
      } else {
        setDiagnosticMessage('Diagnose geslaagd: alle geselecteerde regels zijn verwerkbaar.');
      }
    } catch {
      setDiagnosticMessage('Validatiediagnose kon niet worden uitgevoerd');
    } finally {
      setIsRunningProcessDiagnostic(false);
    }
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
      { naam: spaceName, household_id: householdId },
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

  async function handleRunLayer1() {
    setTestMessage("");
    setShowReport(false);
    try {
      const result = await runLayer1Tests();
      setTestStatus((current) => ({ ...current, ...result }));
      if (!result.started) {
        setTestMessage("Er loopt al een test");
        await refreshTestStatus();
        return;
      }

      setTestMessage("Laag-1 kernregressietest gestart");
      const results = await runLayer1RegressionTests();
      await submitTestResults('layer1', results);
      await refreshTestStatus();
      const latestReport = await fetchLatestTestReport();
      setTestReport(latestReport);
      setShowReport(true);
      setTestMessage('Laag-1 kernregressietest afgerond');
    } catch (error) {
      try {
        await submitTestResults('layer1', [{ name: 'Laag-1 runner', status: 'failed', error: error.message || 'Laag-1 kernregressietest kon niet worden uitgevoerd' }]);
        await refreshTestStatus();
      } catch {
        // negeer secundaire fout
      }
      setTestMessage(error.message || "Laag-1 kernregressietest kon niet worden gestart");
    }
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
      if (!result.started) {
        setTestMessage("Er loopt al een test");
        await refreshTestStatus();
        return;
      }

      setTestMessage("Volledige regressietest gestart");
      const results = await runBrowserRegressionTests();
      await submitTestResults('regression', results);
      await refreshTestStatus();
      const latestReport = await fetchLatestTestReport();
      setTestReport(latestReport);
      setShowReport(true);
      setTestMessage('Volledige regressietest afgerond');
    } catch (error) {
      try {
        await submitTestResults('regression', [{ name: 'Regressietest runner', status: 'failed', error: error.message || 'Regressietest kon niet worden uitgevoerd' }]);
        await refreshTestStatus();
      } catch {
        // negeer secundaire fout
      }
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
              <Button variant="secondary" onClick={async ()=>{await fetch("/api/dev/generate-article-testdata",{method:"POST"});navigate("/voorraad", { replace: false });}}>Artikel testdata</Button>
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
              Start hier een smoke test, een laag-1 kernregressietest of een volledige regressietest en bekijk de laatste status.
            </p>
            <TestRunPanel
              isRunning={testStatus.status === "running"}
              onRunSmoke={handleRunSmoke}
              onRunLayer1={handleRunLayer1}
              onRunRegression={handleRunRegression}
              onViewReport={handleViewReport}
            />
            {testMessage ? <div className="rz-admin-message">{testMessage}</div> : null}
            <TestStatusCard status={testStatus} progress={regressionProgress} />
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
                      <div className="rz-admin-report-main">
                        <span>{result.name}</span>
                        <span>{result.status === "passed" ? "Geslaagd" : result.status === "blocked" ? "Geblokkeerd" : result.status === "skipped" ? "Overgeslagen" : "Gefaald"}</span>
                      </div>
                      {result.triageCategory ? <div className="rz-admin-report-meta-line">Type: {result.triageCategory}</div> : null}
                      {result.error ? <div className="rz-admin-report-meta-line">Fout: {result.error}</div> : null}
                      {result.triageRationale ? <div className="rz-admin-report-meta-line">Analyse: {result.triageRationale}</div> : null}
                      {result.triageSuggestedAction ? <div className="rz-admin-report-meta-line">Advies: {result.triageSuggestedAction}</div> : null}
                    </div>
                  )) : <div className="rz-admin-muted">Nog geen rapport beschikbaar</div>}
                </div>
              </div>
            ) : null}
          </div>

          <div className="rz-admin-panel">
            <h3>Runtime diagnose winkelkoppeling</h3>
            <p className="rz-admin-muted">
              Draai hier gerichte runtime-checks voor locatie-opties in de kassabon en voor geldige verwerkbaarheid van geselecteerde regels.
            </p>
            <div className="rz-admin-actions">
              <Button variant="secondary" onClick={handleRunLocationDiagnostic} disabled={isRunningLocationDiagnostic}>
                {isRunningLocationDiagnostic ? 'Test draait…' : 'Test dropdown-locaties'}
              </Button>
              <Button variant="secondary" onClick={handleRunProcessDiagnostic} disabled={isRunningProcessDiagnostic}>
                {isRunningProcessDiagnostic ? 'Test draait…' : 'Test verwerkvalidatie'}
              </Button>
            </div>
            {diagnosticMessage ? <div className="rz-admin-message">{diagnosticMessage}</div> : null}
            {diagnostics.location ? (
              <div className="rz-admin-report">
                <h4 className="rz-admin-status-title">Laatste dropdown-diagnose</h4>
                <div className="rz-admin-report-meta">
                  <div>Zichtbaar in store-location-options: {diagnostics.location.visible_in_store_location_options ? 'ja' : 'nee'}</div>
                  <div>Huishouden: {diagnostics.location.household_id}</div>
                  <div>Verwachte label: {diagnostics.location.created?.expected_label}</div>
                </div>
              </div>
            ) : null}
            {diagnostics.process ? (
              <div className="rz-admin-report">
                <h4 className="rz-admin-status-title">Laatste validatiediagnose</h4>
                <div className="rz-admin-report-meta">
                  <div>Batch: {diagnostics.process.has_batch ? diagnostics.process.batch_id : 'geen batch'}</div>
                  <div>Geselecteerde regels: {diagnostics.process.selected_lines ?? 0}</div>
                  <div>Zonder geldige locatie: {diagnostics.process.missing_valid_location_count ?? 0}</div>
                  <div>Zonder geldig artikel: {diagnostics.process.missing_article_count ?? 0}</div>
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
