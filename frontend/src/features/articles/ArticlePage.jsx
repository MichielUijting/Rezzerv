
import { useParams } from "react-router-dom";
import { useState } from "react";
import AppShell from "../../app/AppShell";
import ScreenCard from "../../ui/ScreenCard";
import data from "../../demo-articles.json";

export default function ArticlePage(){

 const { articleId } = useParams();
 const article = data.articles.find(a=>String(a.id)===String(articleId)) || data.articles[0];

 const [tab,setTab]=useState("Overzicht");

 const totaal = article.locations.reduce((s,l)=>s+l.aantal,0);

 return (

  <AppShell title="Artikel details" showExit={false}>

    <ScreenCard fullWidth>

      <h2 style={{marginBottom:"10px"}}>{article.name}</h2>

      <div style={{display:"flex",gap:"30px",borderBottom:"1px solid #ccc",marginBottom:"20px"}}>
        {["Overzicht","Voorraad","Locaties","Product","Specificaties","Verpakking","Winkels","Notities"].map(t=>(
          <div
            key={t}
            onClick={()=>setTab(t)}
            style={{
              padding:"6px",
              cursor:"pointer",
              borderBottom:tab===t?"3px solid #1f6f43":"none",
              fontWeight:tab===t?600:400
            }}
          >
            {t}
          </div>
        ))}
      </div>

      {tab==="Overzicht" && (
        <div>
          <p><b>Merk:</b> {article.brand}</p>
          <p><b>Variant:</b> {article.variant}</p>
          <p><b>Artikeltype:</b> {article.type}</p>
          <p><b>Categorie:</b> {article.category}</p>
          <p><b>Subcategorie:</b> {article.subcategory}</p>
          <p><b>Totale voorraad:</b> {totaal}</p>
        </div>
      )}

      {tab==="Voorraad" && (
        <table>
          <thead>
            <tr>
              <th>Locatie</th>
              <th>Sublocatie</th>
              <th>Aantal</th>
            </tr>
          </thead>
          <tbody>
            {article.locations.map((l,i)=>(
              <tr key={i}>
                <td>{l.locatie}</td>
                <td>{l.sublocatie}</td>
                <td>{l.aantal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab==="Locaties" && (
        <ul>
          {article.locations.map((l,i)=>(
            <li key={i}>{l.locatie} → {l.sublocatie}</li>
          ))}
        </ul>
      )}

      {tab==="Product" && (
        <div>
          <p><b>Barcode:</b> {article.barcode}</p>
          <p><b>Fabrikant:</b> {article.manufacturer}</p>
          <p><b>Land van herkomst:</b> {article.country}</p>
        </div>
      )}

      {tab==="Specificaties" && (
        <div>
          <p><b>Gewicht:</b> {article.weight}</p>
        </div>
      )}

      {tab==="Verpakking" && (
        <div>
          <p>Verpakkingstype: onbekend</p>
        </div>
      )}

      {tab==="Winkels" && (
        <div>
          <p>Favoriete winkel: nog niet ingesteld</p>
        </div>
      )}

      {tab==="Notities" && (
        <div>
          <p>Notities voor dit artikel.</p>
        </div>
      )}

    </ScreenCard>

  </AppShell>

 )
}
