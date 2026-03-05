
import { useParams, useNavigate } from "react-router-dom";
import AppShell from "../../app/AppShell";
import ScreenCard from "../../ui/ScreenCard";
import Tabs from "../../ui/Tabs";

export default function ArticlePage() {

  const { articleId } = useParams();
  const navigate = useNavigate();

  return (
    <AppShell title="Artikel details">

      <ScreenCard>

        <div style={{marginBottom:"12px",cursor:"pointer"}}
             onClick={()=>navigate("/voorraad")}>
          ← Voorraad
        </div>

        <Tabs
          tabs={["Overzicht","Voorraad","Locaties","Historie","Analyse"]}
          defaultTab="Overzicht"
        >
          {(tab)=>{

            if(tab==="Overzicht"){
              return <div>Productinformatie komt hier</div>
            }

            if(tab==="Voorraad"){
              return <div>Voorraad per locatie</div>
            }

            if(tab==="Locaties"){
              return <div>Locatiebeheer</div>
            }

            if(tab==="Historie"){
              return <div>Mutatiehistorie</div>
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
