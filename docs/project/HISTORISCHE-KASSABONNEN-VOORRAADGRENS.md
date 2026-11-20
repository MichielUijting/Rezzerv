# PR1 — Historische kassabonnen: voorraadgrens

Status: eerste Draft-implementatie; niet activeren bij bestaande huishoudens of op de draaiende server.
TEST_LEVEL_PROVISIONAL: L
Risico: nieuwe Alembic-tabel en blokkering van fysieke voorraadmutaties bij historische bonnen.

## Productbesluit

- Een nieuw huishouden koppelt AH, Lidl of Jumbo en leest beschikbare historische bonnen in.
- De historie dient voor aankoopgedrag, synoniemen, voorspellingen en een afzonderlijk te berekenen beginvoorraad.
- Geschatte beginvoorraad is geen bewezen voorraad; deze PR schrijft geen voorraadschatting.
- Nieuwe aankopen worden na de ingebruikname normaal via Kassa verwerkt, zonder verplichte voorraadlocatie.
- Waar Inhuis wordt later optioneel ingeschakeld; historische bonnen krijgen nooit achteraf een fysieke locatie.

## Scope van dit eerste codeblok

1. Alembic introduceert `household_receipt_history_cutovers` met een unieke huishoudgrens.
   Na migratie is de tabel leeg. Bestaande huishoudens blijven exact op hun oude gedrag.
2. De classifier gebruikt de oorspronkelijke `receipt_tables.purchase_at` en wijst
   een afgeleide status `historical`, `current`, `review_required` of `legacy` toe.
3. Aankopen op de kalenderdagen vóór `first_current_purchase_date` zijn historisch.
   Op de grensdatum zelf behandelen we aankopen als nieuw; bestaande bonnen bevatten
   geen gegarandeerde tijdzone, waardoor een exact tijdstip niet veilig als autoriteit dient.
   Dit daggrensbesluit moet bij de uiteindelijke onboarding expliciet worden gevalideerd.
4. De bestaande locatievrije Kassa-approvalroute kan historische bonnen goedkeuren
   zonder direct voorraad bij te schrijven. Historische aankoopregels blijven behouden.
5. De gedeelde `purchase-import-batches/{id}/process`-overgang weigert historische
   bonnen en bonnen met onbetrouwbare datum wanneer een grens is ingesteld.
   Dit is tevens de extra beveiliging voor verwerking via Uitpakken.
6. Bij de eerste bevoegde afronding van een nieuw huishouden stelt de backend
   de grens automatisch in, uitsluitend als het huishouden nog geen bonnen,
   voorraad, inventarisbewegingen of importbatches heeft. Dit gebeurt in dezelfde
   transactie als de onboardingafsluiting. Is er wel bestaande data, dan blijft
   de grens ongewijzigd en geldt het bestaande gedrag: geen stille herclassificatie.
7. De server-side Uitpakken-lijst filtert voor huishoudens met een grens historische
   en onbetrouwbaar gedateerde kassabonnen uit. Bronbonnen blijven leesbaar in Kassa.
   Zonder grens blijven alle bestaande rijselecties gelijk.

## Fail-closed eisen

- Geen huishoudoverschrijdende datumclassificatie; de sessie bepaalt het huishouden.
- Bronbonnen en aankoopregels mogen niet worden verwijderd.
- Een bon met ontbrekende of geïmporteerde standaarddatum moet eerst worden herzien.
- Duplicaten blijven onder de bestaande ontvangst-/bronbonidentiteit vallen.
- De legacy-ervaring verandert niet zonder expliciete huishoudgrens.
- De historische scheiding mag nooit via een client-aangeleverd 'is_historical'-veld worden omzeild.

## Nog af te ronden vóór Ready

- Bewijzen dat de routes inclusief bestaande locatiepatches in de PostgreSQL-runtime
  met de verwachte volgorde gemonteerd zijn.
- Historische bonnen na automatische goedkeuring buiten de dagelijkse Uitpakken-werkvoorraad
  houden, met een afzonderlijke leesbare historische status.
- Integratiebewijs voor automatische cutover bij een **nieuw geïsoleerd testhuishouden** voltooien.
- PostgreSQL integratie: historische AH/Lidl/Jumbo-bon leidt tot nul purchase-events,
  nulpunt in voorraad, zelfs na reimport, handmatige goedkeuring of bulkverwerking.
- Datums op de grens, ontbrekende datum, 2 huishoudens, 100 identieke bronbonnen
  en laat binnengekomen oude bonnen verifiëren.
- Gerichte tests, normale CI, patchversiesync, preflight, finale F7 Full (L)
  en PO-acceptatie volgen later vóór Ready/merge.

Geen deployment, feature-activatie of bestaande accountwijziging hoort bij deze PR.

## Datumintegriteit na voorraadverwerking

Bij een geactiveerde historiegrens kan een reeds fysiek verwerkte kassabon
niet met een gewone datumcorrectie naar een datum vóór de grens worden
verplaatst. Een dergelijke wijziging wordt met HTTP 409 afgewezen tot
de bestaande, expliciet gecontroleerde voorraadafhandeling heeft plaatsgevonden.
Daarmee blijft ook de correctieroute consistent met de bronbon-/voorraadgrens.
