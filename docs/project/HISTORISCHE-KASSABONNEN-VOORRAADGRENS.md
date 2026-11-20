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
   de grens uitsluitend in wanneer bonverwerking daadwerkelijk is ingeschakeld
   en nog geen bonnen, voorraad, inventarisbewegingen of importbatches bestaan.
   Het gebeurt in dezelfde transactie als onboarding. Als een huishouden pas
   later bij uitbreiding van zijn mogelijkheden bonverwerking activeert,
   wordt de grens op dat latere moment ingesteld, mits de administratie leeg is.
   Is er al data, dan blijft de grens ongewijzigd: geen stille herclassificatie.
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

## PostgreSQL-testbewijs

De bestaande `Receipt inventory chain merge gate` voert eerst een gerichte
unittest uit en daarna in de wegwerp-PostgreSQL CI-omgeving een DML-only
acceptatietoets met 100 historische bonnen verdeeld over AH/Lidl/Jumbo.
De toets verifieert de kalendergrens, onbetrouwbare datum, bestaande huishoudens,
huishoudisolatie en nul voorraad-/inventory-events. Alle ingevoerde fixtures worden
vóór afronding van de toets teruggedraaid. De volledige receipt→stock-keten en
F7 Full blijven afzonderlijk verplicht; deze gerichte toets vervangt die niet.

## Kassa versus historische raadpleging

Bestaande huishoudens zonder grens behouden hun volledige Kassa-lijst.
Bij nieuwe huishoudens met een eerste-aankoopgrens blijven bonnen met een
betrouwbaar historische aankoopdatum bewaard maar verschijnen niet als
Kassa- of Uitpakken-werkvoorraad. Een onbekende of automatisch ingevulde
standaarddatum blijft wél in Kassa ter controle.

De nieuwe read-only route `GET /api/kassa/historical-receipts-page`
biedt gepagineerde inzage in de werkelijk bewaarde historische bonnen,
alleen voor de geautoriseerde actieve huishoudencontext. Dit is geen
status-/voorraadmutatie en vervangt niet het canonieke receipt-statuscontract.
Een toekomstige onboarding-UI kan deze lijst en de tellers tonen.

De PostgreSQL-acceptatietoets roept daarnaast de werkelijk geregistreerde
`purchase-import-batches/{batch_id}/process`-endpointfunctie aan voor een
historische bon met een geautoriseerde huishoudcontext. Daarmee wordt bewezen
dat ook directe verwerking buiten de Kassa-/Uitpakken-lijst wordt geblokkeerd.

## Concrete routeacceptatie

Een afzonderlijke CI-acceptatie binnen de bestaande tijdelijke PostgreSQL-transactie
roept de geregistreerde goedkeuring van een historische bon aan, probeert deze
opnieuw goed te keuren, leest de echte gepagineerde Kassa- en historische
bonnenroutes, leest de Uitpakken-route en probeert een reeds verwerkte nieuwe
bon terug te dateren naar de historische periode. Er worden ook nieuwe
historische receipt-fixtures toegevoegd als herimportgrenscontrole. De
bestaande ontvangstservice voor echte retailer-API-bonnen is geen onderdeel
van deze gerichte test; de bestaande ontvangst-/reimportcontracten blijven
zelfstandig verplicht. Alles wordt teruggedraaid.
