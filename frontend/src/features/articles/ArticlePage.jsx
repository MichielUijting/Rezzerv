
import { useParams } from "react-router-dom";
import AppShell from "../../app/AppShell";
import ScreenCard from "../../ui/ScreenCard";
import Tabs from "../../ui/Tabs";
import data from "../../demo-articles.json";

export default function ArticlePage(){

  const { articleId } = useParams();
  const article =
    data.articles.find(a => String(a.id) === String(articleId)) ||
    data.articles[0];

  const tabs = [
    "Overzicht",
    "Voorraad",
    "Locaties",
    "Product",
    "Specificaties",
    "Verpakking",
    "Winkels",
    "Notities"
  ];

  const totaal = article.locations.reduce((s,l)=>s+l.aantal,0);

  return (
    <AppShell title="Artikel details" showExit={false}>

      <ScreenCard fullWidth>

        <h2 style={{marginBottom:"16px"}}>{article.name}</h2>

        <Tabs tabs={tabs}>

          {(active)=>{

            if(active==="Overzicht"){
              return (
                <div>
                  <p><strong>Merk:</strong> {article.brand}</p>
                  <p><strong>Variant:</strong> {article.variant}</p>
                  <p><strong>Categorie:</strong> {article.category}</p>
                  <p><strong>Subcategorie:</strong> {article.subcategory}</p>
                  <p><strong>Barcode:</strong> {article.barcode}</p>
                </div>
              );
            }

            if(active==="Voorraad"){
              return (
                <div>
                  <p><strong>Totaal:</strong> {totaal}</p>
                  {article.locations.map((l,i)=>(
                    <div key={i}>
                      {l.locatie} → {l.sublocatie}: {l.aantal}
                    </div>
                  ))}
                </div>
              );
            }

            if(active==="Locaties"){
              return (
                <div>
                  {article.locations.map((l,i)=>(
                    <div key={i}>
                      {l.locatie} → {l.sublocatie}
                    </div>
                  ))}
                </div>
              );
            }

            if(active==="Product"){
              return (
                <div>
                  <p><strong>Type:</strong> {article.type}</p>
                  <p><strong>Land:</strong> {article.country}</p>
                  <p><strong>Fabrikant:</strong> {article.manufacturer}</p>
                </div>
              );
            }

            if(active==="Specificaties"){
              return (
                <div>
                  <p><strong>Gewicht:</strong> {article.weight}</p>
                </div>
              );
            }

            if(active==="Verpakking"){
              return (
                <div>
                  <p>Verpakkingsinformatie volgt.</p>
                </div>
              );
            }

            if(active==="Winkels"){
              return (
                <div>
                  <p>Winkelinformatie volgt.</p>
                </div>
              );
            }

            if(active==="Notities"){
              return (
                <div>
                  <p>Notities bij dit artikel.</p>
                </div>
              );
            }

            return null;
          }}

        </Tabs>

      </ScreenCard>

    </AppShell>
  )
}
