
import React from "react";
import ScreenCard from "../ui/ScreenCard";
import Table from "../ui/Table";

export default function Voorraad() {

  const columns = ["", "Artikel", "Aantal", "Locatie", "Sublocatie"]

  const rows = [
    ["☐","Tomaten",6,"Keuken","Koelkast"],
    ["☐","Pasta",3,"Berging","Voorraadkast"]
  ]

  return (
    <ScreenCard title="Voorraad">

      <Table
        columns={columns}
        rows={rows}
      />

    </ScreenCard>
  )
}
