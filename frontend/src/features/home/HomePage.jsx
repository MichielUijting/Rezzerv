import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'

const tiles = [
  { key: 'bijna-op', label: 'Bijna op', icon: '📉' },
  { key: 'winkelen', label: 'Winkelen', icon: '🛒' },
  { key: 'prognoses', label: 'Prognoses', icon: '📊' },
  { key: 'uitlenen', label: 'Uitlenen', icon: '🔁' },
  { key: 'voorraad', label: 'Voorraad', icon: '📦' },
  { key: 'winkels', label: 'Winkels', icon: '🏬' },
  { key: 'kassabon', label: 'Kassabon', icon: '🧾' },
  { key: 'klantkaarten', label: 'Klantkaarten', icon: '💳' },
  { key: 'recepten', label: 'Recepten', icon: '🍳' },
  { key: 'bestellen', label: 'Bestellen', icon: '📋' },
  { key: 'verlengen', label: 'Verlengen', icon: '⏳' }
]

export default function HomePage() {
  const navigate = useNavigate();
  const [householdName, setHouseholdName] = useState("");
  const [householdError, setHouseholdError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("rezzerv_token");
    if (!token) return;
    fetch("/api/household", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("Huishouden niet beschikbaar");
        return res.json();
      })
      .then((data) => {
        const name = data?.naam || "Mijn huishouden";
        setHouseholdName(name);
        localStorage.setItem("rezzerv_household_name", name);
      })
      .catch(() => {
        setHouseholdError("Huishouden niet beschikbaar");
      });
  }, []);

  return (
    <div className="rz-screen">
      <Header title="Startpagina" />

      <div className="rz-content">
        <div className="rz-content-inner">
          <Card className="rz-card-home">
            <div className="rz-tile-grid" role="navigation" aria-label="Acties">
              {tiles.map(t => (
                <div
                  key={t.key}
                  className="rz-tile"
                  onClick={() => {
                    if (t.key === "voorraad") {
                      navigate("/voorraad");
                    }
                  }}
                  style={{ cursor: t.key === "voorraad" ? "pointer" : "default" }}
                >
                  <div className="rz-tile-icon" aria-hidden="true">{t.icon}</div>
                  <div className="rz-tile-label">{t.label}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
</div>
  )
}


// TABLE ROW HEIGHT DEBUG
setTimeout(()=>{
  try{
    const r=document.querySelector("tbody tr");
    if(r){console.debug("TABLE ROW HEIGHT DEBUG:", r.getBoundingClientRect().height);}
  }catch(e){}
},1000);
