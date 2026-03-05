
import { useState } from "react";

export default function ArticleTabs() {

  const [tab,setTab] = useState("overview");

  return (

    <div>

      <div style={{marginBottom:"20px"}}>

        <button onClick={()=>setTab("overview")}>Overzicht</button>
        <button onClick={()=>setTab("stock")}>Voorraad</button>
        <button onClick={()=>setTab("locations")}>Locaties</button>
        <button onClick={()=>setTab("history")}>Historie</button>
        <button onClick={()=>setTab("analytics")}>Analyse</button>

      </div>

      {tab==="overview" && <div>Productinformatie komt hier</div>}
      {tab==="stock" && <div>Voorraad per locatie komt hier</div>}
      {tab==="locations" && <div>Locatiebeheer komt hier</div>}
      {tab==="history" && <div>Mutatiehistorie komt hier</div>}
      {tab==="analytics" && <div>Analyse volgt later</div>}

    </div>

  );
}
