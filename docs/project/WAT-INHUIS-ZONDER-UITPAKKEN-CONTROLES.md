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
voorraadverwerker. `Direct` is geen fysieke locatie. Bij exacte locaties
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

**Belangrijk risico:** de bestaande directe voorbereiding kan, als er geen
koppeling met een Mijn artikel is, op basis van de bonartikelnaam een
huishoudartikel opzoeken of aanmaken. Zij markeert importregels daarna als
geselecteerd. Dat is **geen vervanging voor een expliciete menselijke
identiteitscontrole**. Een mogelijk onjuiste bonartikelnaam of hoeveelheid moet
dus vóór het goedkeuren in Kassa worden gecorrigeerd. Bestaande code kan
ontbrekende hoeveelheden in de bon-naar-importoverdracht op 1 zetten; dit is
nog geen bewezen veilige vervanging voor de menselijke Uitpakken-review.

Deze PR verandert de bestaande directe match- en voorraadverwerkingssemantiek
niet. Een verdere verscherping van de Kassa-controles voor onzekere bonregels
vereist een aparte acceptatiebeslissing en gerichte ketenproeven.

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
