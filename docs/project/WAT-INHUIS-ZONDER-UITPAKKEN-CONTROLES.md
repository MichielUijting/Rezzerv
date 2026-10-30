# Inhuis — Wat Inhuis zonder Uitpakken: controle- en behoudsgrenzen

**Doel:** verifieer welke controles blijven bestaan wanneer een huishouden
Uitpakken uitschakelt en goedgekeurde kassabonnen direct in Voorraad verwerkt.
Dit document beschrijft de bestaande codepaden en de in deze PR toegevoegde
veiligheidsgrenzen; het is geen bewering dat een nog niet uitgevoerde regressie
al geslaagd is.

## Ketens

- **Uitpakken aan:** bon importeren → Kassa controleren/goedkeuren →
  Uitpakken met menselijke review (Mijn artikel, hoeveelheid/prijs, artikelgroep,
  locatietoewijzing en batchacties) → centrale purchase-importverwerker → Voorraad.
- **Uitpakken uit:** bon importeren → Kassa controleren/goedkeuren →
  `receipt_direct_inventory_approval_patch` bereidt de bonbatch voor →
  **dezelfde** centrale `process_purchase_import_batch` →
  `inventory_events` en Voorraad.

De directe route is uitsluitend bedoeld voor huishoudens met kassabonverwerking,
voorraadregistratie, `unpacking_enabled=false` en locatieniveau `none` of
`global`. Voor reguliere voorraadregels gaat de nieuwe voorraadpositie
locatievrij (`space_id=NULL`, `sublocation_id=NULL`) naar de bestaande
voorraadverwerker. Dit geldt **ook bij `global`**: zonder de
locatietoewijzing van Uitpakken krijgen nieuwe bonartikelen niet automatisch
een hoofdlocatie. `Direct` is geen fysieke locatie. Bij exacte locaties
blijft Uitpakken verplicht.

## Wat blijft bestaan?

| Controle of garantie | Zonder Uitpakken |
|---|---|
| Bronbon / scanner / parser en duplicaatcontrole | Blijft vóór Kassa bestaan |
| Goedkeuren in Kassa | Blijft nodig; winkel en aankoopdatum zijn verplicht |
| Bonregels met financiële betekenis uit de voorraadketen weren | Bestaande `derive_receipt_line_semantics` bepaalt welke regels voorraadgeschikt zijn |
| Bonbedrag versus som regels | Kassa controleert dit; **handmatig goedkeuren kan expliciet een afwijking accepteren** |
| Huishoudbevoegdheid | Bestaande Kassa- en importverwerker-autorisatie blijft gelden |
| Artikelidentiteit, hoeveelheid en geldige artikelgroep | De centrale verwerker controleert geldigheid en meldt mislukte regels |
| Voorraadboeking en herleidbaarheid | Bestaande centrale verwerker schrijft aankoopgebeurtenis en voorraadpositie |
| Dubbelboeken voorkomen | Reeds verwerkte regels/gebeurtenissen worden niet opnieuw geboekt; herhaalde goedkeuring van afgehandelde bon is een no-op |
| Dagartikelen / direct verbruik | De bestaande verwerker houdt `DIRECT_CONSUMPTION` buiten fysieke voorraad |
| Foutmelding bij mislukte directe verwerking | De directe route geeft een fout bij `failed_count` of `skipped_count`; reeds geboekte regels worden niet dubbel verwerkt |

## Wat vervalt als afzonderlijk controlemoment?

- Per bonartikel in **Uitpakken** een voorgestelde Mijn-artikelkoppeling
  bekijken en aanpassen.
- Hoeveelheid/prijs bij het uitpakken nalopen en daar aanpassen.
- Artikelgroep en opslaglocatie bij het uitpakken bevestigen.
- Selecteren, in bulk corrigeren en afzonderlijk naar Voorraad verwerken.

## Centrale controles achter de schermen

Beide routes gebruiken `receipt_stock_review_service.py` en dezelfde
`process_purchase_import_batch`-verwerker. De gedeelde beslissingen zijn:

1. **Artikelidentiteit:** een expliciet bevestigd huishoudartikel-ID, een
   bestaand bevestigd winkelgeheugen of een aantoonbaar catalogusgekoppeld
   product. De bronbontekst is hoogstens een naam voor een **nieuw**
   huishoudartikel na expliciete Kassa-goedkeuring; gelijke tekst is geen
   bewijs om bestaande huishoudartikelen automatisch samen te voegen.
2. **Hoeveelheid:** de gemeenschappelijke normalisator controleert dat een
   hoeveelheid aanwezig, eindig, positief en passend bij de eenheid is.
   Stuksaantallen moeten gehele getallen zijn. Gewicht/volume blijft per
   aankoopverpakking een voorraadstuk, conform het bestaande voorraadmodel.
   Een ontbrekend aantal wordt bij directe Kassa-goedkeuring niet als
   `1` ingevuld: Kassa weigert dan met een concrete herstelmelding.
3. **Afhandeling:** niet-voorraadregels blijven uitgesloten; de centrale
   importverwerker valideert artikel en artikelgroep en schrijft
   household-scoped events, historie en voorraadposities.
4. **Herhalingen:** reeds verwerkte regels en bonnen mogen geen extra
   voorraadgebeurtenis opleveren.

**Uitzonderingen:** wanneer de bron onvoldoende bewijs biedt (bijvoorbeeld
een ontbrekend aantal of een bestaande naam zonder bevestigde match), wordt
de automatische route niet als succesvol gepresenteerd. De bon moet dan
via de bestaande Kassa-correctie worden behandeld. Er verschijnt **geen**
nieuw Uitpakken-scherm en er wordt niet gegokt.

De aparte menselijke mogelijkheid om artikelgroep of plaats per bonregel in
Uitpakken te wijzigen vervalt. Bij `location_tracking_level=none` worden
geen locatiegegevens vereist of verzonnen. Het ontbreken van een
Uitpakken-scherm betekent niet dat de validaties worden overgeslagen.


## Veilig terugschakelen bij bestaande voorraad

De instelling wordt alleen door een bevoegd **huishoud-Beheerder** gewijzigd,
via de bestaande sessie- en `household_settings.manage`-grens.

- Een wijziging wist/archiefeert **geen** locaties, artikelrelaties,
  voorraadposities, events, bonnen of historie.
- Bij nog open bonregels die anders uit het Uitpakken-pad zouden verdwijnen
  weigert de server de omschakeling.
- Bij bestaande actieve voorraad die op locaties ligt weigert de server een
  neerwaartse locatieswitch. Anders zouden locatiegebonden en locatievrije
  posities naast elkaar kunnen gaan bestaan zonder veilige, geteste
  voorraadconversie.
- `exact` met Uitpakken uit wordt geweigerd, omdat de directe route dan geen
  geldige doellocatie kan toekennen.
- Locatiegegevens blijven bestaan wanneer een veilig huishouden zijn
  locatiegebruik uitschakelt, en kunnen later opnieuw worden gebruikt.
- Er is **geen** automatische, destructieve voorraadconversie of herschikking.

## Vereiste kwaliteitsbewijzen voor Ready

- PostgreSQL regressie voor de huishoudinstelling en huishoudenisolatie.
- Locatie- en Uitpakken-aan/uit-matrix in navigatie en Settings.
- Bestaande Wat Inhuis Kassa→Voorraad regressie voor directe verwerking,
  dubbele goedkeuring, historie en handmatig toegevoegd artikel.
- Bestaande kassabonketen en receipt-/inventory-regressies.
- Frontend build, relevante rol-/sessietests, versie/sync en toepasselijke
  L-risicogates inclusief F7 op de definitieve kandidaat.

Nieuwe of bestaande fails betekenen: Draft houden, concreet repareren en gericht
opnieuw testen. Een succesvolle compile/CI-proef alleen vervangt geen
functionele PO-acceptatie.
