# Aldi — geen digitale winkelkoppeling

## Besluit product owner
De eerder voorgestelde Shop & Go-e-mailbonroute is teruggetrokken. Voor
reguliere Aldi-bezoeken is geen betrouwbare, algemene digitale kassabonvoorziening
vastgesteld. Een automatische digitale Aldi-koppeling wordt niet aangeboden.

## Scherm Instellingen → Winkelkoppelingen
Aldi blijft zichtbaar met de melding:
"Aldi ondersteunt geen digitale kassabonnen voor reguliere winkelkoppelingen. Een koppeling met Inhuis is daarom niet mogelijk."

De actie is uitgeschakeld. Ook als er historische generieke Aldi-koppelingdata
bestaan, presenteert de UI deze niet als werkende digitale verbinding.
Er worden geen historische gebruikersgegevens verwijderd.

## Behouden functionaliteit
De bestaande algemene Kassa-scanner en Aldi-profielen voor papieren bonnen
blijven onaangetast. Eerdere toevoegingen van een Aldi Shop & Go-uploadscherm,
bijbehorende frontendhelper, specifieke contracttests en workflow vervallen.
De generieke bestaande Kassa-import blijft onafhankelijk beschikbaar.

## Tests
`node frontend/tests/store-connections.contract.mjs` controleert de neutrale
niet-beschikbaarstatus, de uitgeschakelde actie, het ontbreken van Aldi-upload
en de bestaande AH/Lidl-tabellen.

De beschikbaarheid van toekomstige digitale Aldi-diensten kan later opnieuw
worden onderzocht. Deze wijziging claimt niet dat geen enkele Aldi-vestiging
wereldwijd ooit digitale bonnen verstrekt.
