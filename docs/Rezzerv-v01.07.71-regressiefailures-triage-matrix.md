# Rezzerv v01.07.71 — regressiefailures triage matrix

Deze matrix classificeert de resterende Admin-regressiefailures in drie typen:
- test-isolatieprobleem
- functionele bug
- verouderde of te harde testverwachting

| Scenario | Classificatie | Analyse | Advies vervolg |
|---|---|---|---|
| Handmatige voorraadcorrectie blijft persistent en zichtbaar in historie | test-isolatieprobleem | Exacte voorraad- en historieverwachting blijft gevoelig voor fixture-afwijkingen en projectievertraging. | Isoleer scenario op eigen fixture of valideer via event-id. |
| Huishoudinstelling aan + follow_household → automatische afboeking zichtbaar | functionele bug | Analyse-status slaagt, maar verwacht historie-/eventeffect ontbreekt. | Controleer eventcreatie en projectie bij follow_household. |
| Artikeloverride always_on → automatische afboeking zichtbaar bij huishoudinstelling uit | functionele bug | Override-readstatus klopt, maar verwacht automatische event ontbreekt. | Controleer override always_on op daadwerkelijke eventregistratie. |
| Vereenvoudigingsniveau gebalanceerd vult bekende regels automatisch in | verouderde of te harde testverwachting | Test leunt op precieze prefill-status en UI-labels. | Versoepel selectors of update actuele verwachting. |
| Vereenvoudigingsniveau maximaal gemak bereidt bekende regels automatisch voor maar verwerkt niet stil | verouderde of te harde testverwachting | Test leunt op specifieke suggestiestatus en exact gelijkblijvende voorraad. | Bevestig actueel gedrag en verlaag afhankelijkheid van labeltekst. |
| Winkelimport toont uitleg bij bekende regel met alleen voorstel | verouderde of te harde testverwachting | Copy/uitleg-check is gevoelig voor tekstwijzigingen zonder functionele breuk. | Maak check semantischer of actualiseer verwachting. |
| Winkelwaarschuwing Terug annuleert verwerking zonder voorraadeffect | functionele bug | Specifiek gebruikerspad werkt nog niet stabiel zonder side-effect. | Controleer modalactie Terug en procestriggering. |
| Winkelwaarschuwing Negeren verwerkt alleen complete regels | functionele bug | Partiële verwerking lijkt nog niet strikt gescheiden. | Controleer ready_only-verwerking en batchstatus per regel. |
| Winkelvelden en waarschuwingen volgen de styleguide | functionele bug | Deze check weerspiegelt een expliciete PO-eis op echte UI-uitvoer. | Controleer store-veldclasses, focusstijl en modalomkadering. |
| Nulvoorraad blijft zichtbaar tot Voorraad opnieuw opent | test-isolatieprobleem | Scenario combineert inline state en route-heropen op gemuteerde voorraadset. | Houd scenario op eigen schone voorraadfixture en log overgang expliciet. |
| Lidl-flow kan een regel koppelen en naar voorraad verwerken | functionele bug | Kernflow winkelverwerking is nog niet reproduceerbaar dicht. | Controleer koppeling, locatiekeuze, process-endpoint en voorraadeffect. |
| Jumbo-flow kan een regel koppelen en naar voorraad verwerken | functionele bug | Zelfde kernflowprobleem als Lidl, maar dan op Jumbo-pad. | Controleer rule readiness en projectie naar actuele voorraad. |
| Winkelimport bewaart twee losse events voor hetzelfde artikel en Historie toont beide | functionele bug | Verwachting raakt echt eventbehoud en historiepresentatie. | Controleer aparte inventory_events en rendering van beide historie-items. |
