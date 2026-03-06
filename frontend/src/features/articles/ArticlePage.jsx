
import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import AppShell from "../../app/AppShell";
import ScreenCard from "../../ui/ScreenCard";
import Tabs from "../../ui/Tabs";

export default function ArticlePage() {

  const { articleId } = useParams();

  const [artikel,setArtikel]=useState(null);
  const [rows,setRows]=useState([]);

  useEffect(()=>{

    fetch("/api/dev/inventory-preview")
      .then(r=>r.json())
      .then(data=>{

        const all=data.rows || [];

        const selected=all.find(r=>String(r.id)===String(articleId));

        if(!selected){
          return;
        }

        const artikelNaam=selected.artikel;

        const artikelRows=all.filter(r=>r.artikel===artikelNaam);

        setArtikel(artikelNaam);
        setRows(artikelRows);

      });

  },[articleId]);

  const totaal = rows.reduce((s,r)=>s + Number(r.aantal||0),0);

  return (
    <AppShell title="Artikel details" showExit={false}>

      <ScreenCard>

        <h2 style={{marginBottom:"10px"}}>{artikel || "Artikel"}</h2>

        <Tabs
          tabs={["Overzicht","Voorraad","Locaties","Historie","Analyse"]}
          defaultTab="Overzicht"
        >
          {(tab)=>{

            if(tab==="Overzicht"){
              return (
                <div>
                  <div>Totaal in huis: <strong>{totaal}</strong></div>
                  <div>Aantal locaties: {rows.length}</div>
                </div>
              )
            }

            if(tab==="Voorraad"){
              return (
                <table className="rz-table">
                  <thead>
                    <tr>
                      <th>Locatie</th>
                      <th>Sublocatie</th>
                      <th>Aantal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(r=>(
                      <tr key={r.id}>
                        <td>{r.locatie}</td>
                        <td>{r.sublocatie}</td>
                        <td>{r.aantal}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            }

            if(tab==="Locaties"){
              return (
                <ul>
                  {rows.map(r=>(
                    <li key={r.id}>
                      {r.locatie} → {r.sublocatie}
                    </li>
                  ))}
                </ul>
              )
            }

            if(tab==="Historie"){
              return <div>Historie volgt later</div>
            }

            if(tab==="Analyse"){
              return <div>Analyse volgt later</div>
            }

          }}
        </Tabs>

      </ScreenCard>

    </AppShell>
  );
}
