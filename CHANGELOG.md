- v01.10.42: Beheer → Ruimtes nu in Voorraad-tabelstijl met groene selectiecheckboxes, multi-select, acties onder de tabel, CSV-export en alleen toegankelijk voor Admin.
- v01.10.40: Barcode stabilisatiepatch op basis van v01.10.39; camera-start gebruikt nu constraint fallback voor Firefox/laptop, barcode-lookup gebruikt indien beschikbaar OpenFoodFacts en onbekende barcodes vullen geen verzonnen artikelnummers meer in.
- v01.10.40: Complete cumulatieve release op basis van v01.10.37 met integratie van de barcodecamera-foutafhandeling uit v01.10.38; camerafouten tonen nu nette Nederlandstalige Rezzerv-meldingen in de overlay en ruwe technische foutteksten worden intern gelogd.
# Rezzerv v01.10.40 - complete cumulatieve release t/m barcodecamera foutafhandeling

## Doel van deze release
Een complete en zelfstandige release opleveren die packagingmatig aansluit op v01.10.37 en functioneel de verbeterde barcodecamera-foutafhandeling uit v01.10.38 bevat.

## Inbegrepen in deze release
- volledige packagingbasis van v01.10.37 behouden
- barcodecamera blijft werken via getUserMedia + ZXing
- camerafouten tonen nette Nederlandstalige Rezzerv-meldingen in de overlay
- technische foutdetails worden intern gelogd
- meldingen blijven binnen de overlay
- versies opgehoogd naar v01.10.40

## Niet gewijzigd
- kassabonbatchflow
- backend-endpoints voor purchase-events
- rollen/rechten/privacy
- onderhoudsschermen voor ruimtes/sublocaties


## v01.10.41
- Beheer → Ruimtes toegevoegd
- Actieve ruimtes gekoppeld aan locatie-dropdowns
- Verwijderblokkade bij gekoppelde voorraad of sublocaties

## v01.10.43 - UI-correcties Beheer Ruimtes
- alle checkboxes in Ruimtes groen gemaakt, inclusief overlay en Actief-kolom
- Exporteren nu alleen actief bij geselecteerde ruimtes
- toelichtende gebruikstekst verwijderd
- Terug-knop verwijderd
- Actief-filter gewijzigd naar checkbox-gebaseerd Ja/Nee filter

## v01.10.44
- Beheer Ruimtes: tabelmarges, paddings en kolombreedtes gelijkgetrokken met Voorraad.
- Ruimteskaart verbreed zodat filterrij en kolommen niet meer overlappen.

## v01.10.45
- Herstelt crash in Instellingen > Huishouden door ontbrekende import en foutieve dismiss-hook referenties.
