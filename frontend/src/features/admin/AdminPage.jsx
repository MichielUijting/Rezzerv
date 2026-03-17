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
  runLayer2Tests,
  runLayer3Tests,
  runRegressionTests,
  runSmokeTests,
  submitTestResults,
} from "./services/adminTestingService";
import { runBrowserSmokeTests } from "./lib/browserSmokeRunner";
import { runLayer1RegressionTests } from "./lib/layer1RegressionRunner";
import { runLayer2RouteTests } from "./lib/layer2RouteRunner";
import { runLayer3StyleguideTests } from "./lib/layer3StyleguideRunner";
import { runBrowserRegressionTests } from "./lib/browserRegressionRunner";


const REMOVED_LEGACY_ITEMS = [
  { name: 'Quick action “Volledige regressietest uitvoeren” uit leidend testpaneel', reason: 'Admin-ingang verwijderd; laag 1/2/3 zijn leidend, legacy blijft alleen in eigen blok beschikbaar.' },
  { name: 'Legacy-matrixregels voor login / voorraad / artikeldetail openen', reason: 'Gedekt door laag 1 en daarom niet meer als losse legacy-regel zichtbaar.' },
  { name: 'Legacy-matrixregel voor admin / testpaneel opent', reason: 'Gedekt door laag 2 en daarom niet meer als losse legacy-regel zichtbaar.' },
  { name: 'Legacy-matrixregel voor kernscherm UI-structuur', reason: 'Gedekt door laag 3 en daarom niet meer als losse legacy-regel zichtbaar.' },
]

const MIGRATED_LEGACY_ITEMS = [
  { name: 'Runtime diagnose dropdown-locaties', targetLayer: 'Laag 2', reason: 'Overgenomen als aparte admin-routecheck voor zichtbaarheid en bruikbare niche-ingang.' },
  { name: 'Runtime diagnose verwerkvalidatie', targetLayer: 'Laag 2', reason: 'Overgenomen als aparte admin-routecheck voor zichtbaarheid en bruikbare niche-ingang.' },
]

const LEGACY_REGRESSION_MATRIX = [
  { name: 'Legacy runner voor gecombineerde regressie', classification: 'Legacy', coverage: 'Referentie / diagnosehulp voor resterende nichechecks', action: 'Niet leidend; alleen nog starten vanuit legacy-blok' },
  { name: 'Overige verouderde debug- of admin-ingangen rond legacy-runs', classification: 'Verwijderkandidaat', coverage: 'Geen productleidende dekking nodig', action: 'Pas schrappen als bevestigd is dat niemand hier nog op leunt' },
]

const LEGACY_CLASSIFICATION_ORDER = ['Legacy', 'Verwijderkandidaat']

function summarizeLegacyMatrix(items) {
  return LEGACY_CLASSIFICATION_ORDER.map((label) => ({
    label,
    count: items.filter((item) => item.classification === label).length,
  })).filter((item) => item.count > 0)
}

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


  async function handleRunLayer2() {
    setTestMessage("");
    setShowReport(false);
    try {
      const result = await runLayer2Tests();
      setTestStatus((current) => ({ ...current, ...result }));
      if (!result.started) {
        setTestMessage("Er loopt al een test");
        await refreshTestStatus();
        return;
      }

      setTestMessage("Laag-2 route-/schermtest gestart");
      const results = await runLayer2RouteTests();
      await submitTestResults('layer2', results);
      await refreshTestStatus();
      const latestReport = await fetchLatestTestReport();
      setTestReport(latestReport);
      setShowReport(true);
      setTestMessage('Laag-2 route-/schermtest afgerond');
    } catch (error) {
      try {
        await submitTestResults('layer2', [{ name: 'Laag-2 runner', status: 'failed', error: error.message || 'Laag-2 route-/schermtest kon niet worden uitgevoerd' }]);
        await refreshTestStatus();
      } catch {
      }
      setTestMessage(error.message || "Laag-2 route-/schermtest kon niet worden gestart");
    }
  }


  async function handleRunLayer3() {
    setTestMessage("");
    setShowReport(false);
    try {
      const result = await runLayer3Tests();
      setTestStatus((current) => ({ ...current, ...result }));
      if (!result.started) {
        setTestMessage("Er loopt al een test");
        await refreshTestStatus();
        return;
      }

      setTestMessage("Laag-3 UI/styleguide-test gestart");
      const results = await runLayer3StyleguideTests();
      await submitTestResults('layer3', results);
      await refreshTestStatus();
      const latestReport = await fetchLatestTestReport();
      setTestReport(latestReport);
      setShowReport(true);
      setTestMessage('Laag-3 UI/styleguide-test afgerond');
    } catch (error) {
      try {
        await submitTestResults('layer3', [{ name: 'Laag-3 runner', status: 'failed', error: error.message || 'Laag-3 UI/styleguide-test kon niet worden uitgevoerd' }]);
        await refreshTestStatus();
      } catch {
      }
      setTestMessage(error.message || "Laag-3 UI/styleguide-test kon niet worden gestart");
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
      <div data-testid="admin-page">
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
              Start hier een smoke test of een leidende laag-1, laag-2 of laag-3 regressietest en bekijk de laatste status.
            </p>
            <div data-testid="test-run-panel"><TestRunPanel
              isRunning={testStatus.status === "running"}
              showLegacyWarning
              onRunSmoke={handleRunSmoke}
              onRunLayer1={handleRunLayer1}
              onRunLayer2={handleRunLayer2}
              onRunLayer3={handleRunLayer3}
              onViewReport={handleViewReport}
            />
            </div>
            {testMessage ? <div className="rz-admin-message">{testMessage}</div> : null}
            <TestStatusCard status={testStatus} progress={regressionProgress} />
            {showReport && testReport ? (
              <div className="rz-admin-report">
                <h4 className="rz-admin-status-title">Laatste testrapport</h4>
                <div className="rz-admin-report-meta">
                  <div>Testtype: {testReport.test_type || "Onbekend"}</div>
                  <div>Leidend: laag 1 / laag 2 / laag 3</div>
                  <div>Legacy volledige regressierun: alleen referentie</div>
                  <div>Laatste run: {testReport.last_run_at ? new Date(testReport.last_run_at).toLocaleString("nl-NL") : "Nog geen rapport"}</div>
                  <div>Geslaagd: {testReport.results?.filter((result) => result.status === "passed").length || 0}</div>
                  <div>Gefaald: {testReport.results?.filter((result) => result.status === "failed").length || 0}</div>
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



          <div className="rz-admin-panel" data-testid="legacy-regression-panel">
            <h3>Legacy regressiesuite</h3>
            <p className="rz-admin-muted">
              Oude regressietests zijn bevroren als legacy. Laag 1, laag 2 en laag 3 zijn leidend; legacy blijft alleen beschikbaar voor resterende nichechecks en diagnosehulp.
            </p>
            <div className="rz-admin-actions">
              <Button variant="secondary" onClick={handleRunRegression} disabled={testStatus.status === "running"}>
                Legacy nichechecks uitvoeren
              </Button>
            </div>
            <div className="rz-admin-report">
              <h4 className="rz-admin-status-title">Legacy-matrix</h4>
              <div className="rz-admin-report-meta" data-testid="legacy-regression-summary">
                {summarizeLegacyMatrix(LEGACY_REGRESSION_MATRIX).map((item) => (
                  <div key={item.label}>{item.label}: {item.count}</div>
                ))}
              </div>
              <div className="rz-admin-report-list">
                {LEGACY_REGRESSION_MATRIX.map((item) => (
                  <div key={item.name} className="rz-admin-report-row rz-admin-report-row--neutral">
                    <div className="rz-admin-report-main">
                      <span>{item.name}</span>
                      <span>{item.classification}</span>
                    </div>
                    <div className="rz-admin-report-meta-line">Dekking: {item.coverage}</div>
                    <div className="rz-admin-report-meta-line">Actie: {item.action}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="rz-admin-report" data-testid="legacy-migration-list">
              <h4 className="rz-admin-status-title">Migratielijst v1</h4>
              <div className="rz-admin-report-list">
                {MIGRATED_LEGACY_ITEMS.map((item) => (
                  <div key={item.name} className="rz-admin-report-row rz-admin-report-row--neutral">
                    <div className="rz-admin-report-main">
                      <span>{item.name}</span>
                      <span>{item.targetLayer}</span>
                    </div>
                    <div className="rz-admin-report-meta-line">Reden: {item.reason}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rz-admin-report" data-testid="legacy-removal-list">
              <h4 className="rz-admin-status-title">Verwijderlijst v1</h4>
              <div className="rz-admin-report-list">
                {REMOVED_LEGACY_ITEMS.map((item) => (
                  <div key={item.name} className="rz-admin-report-row rz-admin-report-row--neutral">
                    <div className="rz-admin-report-main">
                      <span>{item.name}</span>
                      <span>Verwijderd</span>
                    </div>
                    <div className="rz-admin-report-meta-line">Reden: {item.reason}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rz-admin-panel" data-testid="admin-runtime-diagnostics-panel">
            <h3>Runtime diagnose winkelkoppeling</h3>
            <p className="rz-admin-muted">
              Draai hier gerichte runtime-checks voor locatie-opties in de kassabon en voor geldige verwerkbaarheid van geselecteerde regels.
            </p>
            <div className="rz-admin-actions">
              <Button variant="secondary" onClick={handleRunLocationDiagnostic} disabled={isRunningLocationDiagnostic} data-testid="admin-diagnostic-location-button">
                {isRunningLocationDiagnostic ? 'Test draait…' : 'Test dropdown-locaties'}
              </Button>
              <Button variant="secondary" onClick={handleRunProcessDiagnostic} disabled={isRunningProcessDiagnostic} data-testid="admin-diagnostic-process-button">
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
      </div>
    </AppShell>
  );
}
