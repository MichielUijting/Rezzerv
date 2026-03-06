import React, { useEffect, useState } from "react";
import AppShell from "../../app/AppShell";
import Card from "../../ui/Card";
import Button from "../../ui/Button";
import Input from "../../ui/Input";

export default function AdminPage() {
  const [status, setStatus] = useState({ spaces: 0, sublocations: 0, inventory: 0 });
  const [message, setMessage] = useState("");

  const [spaceName, setSpaceName] = useState("");
  const [spaceId, setSpaceId] = useState("");
  const [sublocationName, setSublocationName] = useState("");

  const [artikel, setArtikel] = useState("");
  const [aantal, setAantal] = useState("");
  const [inventorySpaceId, setInventorySpaceId] = useState("");
  const [inventorySublocationId, setInventorySublocationId] = useState("");

  async function fetchStatus() {
    try {
      const res = await fetch("/api/dev/status");
      const data = await res.json();
      setStatus(data);
    } catch {
      setMessage("Status niet beschikbaar");
    }
  }

  useEffect(() => {
    fetchStatus();
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
              <Button variant="secondary" onClick={handleReset}>Reset demo data</Button>
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
