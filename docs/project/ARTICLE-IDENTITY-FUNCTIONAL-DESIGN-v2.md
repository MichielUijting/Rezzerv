# Inhuis — functioneel ontwerp artikelidentificatie v2.0

**Besloten door de Product Owner: 12 november 2026.**
**Status: vastgesteld doelontwerp, niet volledig geïmplementeerd.**
Dit document legt de 27 in de projectgesprekken vastgestelde keuzes vast. De
technische uitvoering wordt in afgebakende fasen en afzonderlijke Draft-PR's
opgeleverd. Het document overschrijft geen hardere security-, household- of
identitycontracten.

## 1. Domeinen en identiteit

1. **1A — Opgeslagen barcode is bewijs.** Bewaren in **Identificeren** is al
   de expliciete vaststelling van de barcode. Geen extra OFF- of
   GS1-classificatiecheck, en geen tweede bevestigingshandeling.
2. **2A — Eén bewezen mondiale GTIN, één Catalogusproduct.** Dezelfde
   mondiale productidentiteit mag geen dubbele centrale producten maken.
3. **3A — Bestaande identiteit hergebruiken.** Eerst zoeken op bewezen
   barcode/productidentiteit; alleen zonder bestaand eenduidig product een
   nieuw Catalogusproduct aanmaken.
4. **4A — Identiteit staat los van classificatie.** Ontbrekende GS1 GPC of
   CBS ECOICOP verhindert geen bewezen barcode-identificatie.
5. **Uitwisselbaarheid is productspecifiek.** Bijvoorbeeld gewone,
   biologische, groene en gele courgette kunnen voor de relevante
   huishoudbehoefte uitwisselbaar zijn; diepvriesproducten, maaltijdmixen
   en babyvoeding zijn daardoor niet automatisch equivalent.
6. **6B — Alleen sterke semantische synoniemen automatisch.** Bij twijfel
   is beoordeling nodig en wordt geen stilzwijgende relatie vastgelegd.
7. **7A — Niet herkende bonartikelen blijven zichtbaar.** Een gedeeltelijk
   geslaagde matching mag andere bonartikelen niet laten verdwijnen.
8. **8A — Huishoudhistorie behouden.** Bestaande huishoudartikelen en hun
   historie blijven behouden; productidentificatie is geen toestemming
   om ze op naam samen te voegen of te verwijderen.
9. **9A — Handmatige correctie heeft voorrang met registratie.** Een
   bewuste vervanging van een bestaande koppeling moet aantoonbaar en
   herleidbaar zijn, nooit een stille overschrijving.
10. **10B — Productsoort én uitwisselbaarheid.** Semantische matching
    vereist betrouwbare productsoort én feitelijke uitwisselbaarheid; een
    gelijke tekst of categorie alleen is onvoldoende.
11. **11A — Centrale synoniemen.** Bevestigde productrelaties zijn centrale
    Cataloguskennis en bruikbaar voor alle huishoudens, zonder
    huishoudspecifieke data te delen.
12. **12B — Bestaande andere productidentiteit.** Een barcodecorrectie die
    een ander bestaand Catalogusproduct raakt vereist vooraf een expliciete,
    bevoegde gevolgencontrole en bevestiging.
13. **13B — Verpakkingsgroottes.** Producten met afwijkende grootte kunnen
    binnen een passende synoniemrelatie vallen, mits de hoeveelheden met
    een bewezen toegestane factor worden omgerekend.

## 2. Scope, synoniemen, correcties en historisch herstel

14. **14A — Mondiaal versus beperkt geldig.** Barcode met een geldig
    controlecijfer is niet vanzelf wereldwijd uniek. Lidl-/winkelinterne
    codes worden per artikel in **Identificeren** door de PO beoordeeld en
    later waar nodig gecorrigeerd; niet automatisch gepromoveerd tot
    mondiale GTIN. De eenmaal bewaarde code telt wel als bewijs voor
    zijn specifieke winkelcontext.
15. **15A — Toetsbare semantische regels.** Automatische productregels
    zijn expliciet, beperkt en met voorbeelden/regressies onderbouwd.
16. **16B — Transitieve relaties bewaken.** Een synoniemketen mag niet
    via transitiviteit een verboden of tegenstrijdige productcombinatie
    creëren.
17. **17B — Geverifieerde standaardfactoren.** Voor geschikte families
    zijn goedgekeurde schattingen of standaardhoeveelheidsfactoren
    toegestaan; geen onbeperkte afleiding uit een naam.
18. **18A — Verhoogde bevoegdheden.** Centrale identiteitscorrecties
    krijgen server-side beveiliging en een gecontroleerd correctiepad.
19. **19B — Historische doorwerking.** Na een aantoonbaar correcte
    identiteitswijziging worden de relevante oude bon-/voorraadverwijzingen
    waar veilig mogelijk automatisch hersteld, niet blind herschreven.
20. **20A — Voorraad en Bijna op.** Bewezen synoniemen worden volgens
    de instellingen van het betreffende huishouden meegenomen bij
    voorraadverbruik en Bijna op, met huishoudenisolatie en idempotentie.
21. **21A — Onbekend blijft onbekend.** Zonder voldoende identiteit
    blijft de status **Nog identificeren** en wordt niets fictief gekoppeld.
22. **22A — Winkelinterne scope per keten.** Dezelfde beperkte code
    bij twee winkels is niet automatisch hetzelfde product.
23. **23A — Alleen geteste productfamilies.** Productfamilie-extrapolatie
    is beperkt tot expliciet toegestane en geteste gevallen.
24. **24A — Verboden transitieve groep blokkeren.** Niet alleen de
    directe koppeling, ook de volledige resulterende synoniemgroep wordt
    op verboden combinaties gecontroleerd.
25. **25A — Alleen goedgekeurde factoren.** Een omrekening mag alleen
    gebruikmaken van expliciete betrouwbare conversiefactoren.
26. **26A — Herstel afgeleiden, niet bronbewijs.** Bij historisch herstel
    worden verwijzingen gecorrigeerd en afgeleide voorraadresultaten
    herberekend; oorspronkelijke bonnen, aankopen en andere brongegevens
    blijven controleerbaar intact.
27. **27B — Wie mag corrigeren.** Zowel de actieve platform-Superuser
    als **actieve, uitdrukkelijk geautoriseerde Frontteamleden** kunnen
    centrale barcodecorrecties uitvoeren, met gevolgenoverzicht,
    bevestiging en registratie. Alleen een frontendknop is nooit voldoende
    autorisatie.

## 3. Sleutels, scheiding en invarianten

- Het centrale Catalogusproduct is niet het huishoudartikel; voorraad
  blijft verankerd aan het canonieke \`household_articles.id\` binnen het
  eigen huishouden.
- Een winkel/bonartikelidentiteit is de combinatie **winkelketen +
  kassabonomschrijving + bonartikelnummer**. Dezelfde omschrijving mag
  meerdere bonartikelnummers hebben; een gegeven exacte combinatie mag
  hoogstens één bevestigde artikel-/barcode-identiteit hebben.
- Een bonartikelnummer is geen barcode. Een beperkte Lidl-code wordt
  niet automatisch een wereldwijd unieke identiteit.
- Onzekerheden, conflicten en ontbrekend bewijs blokkeren mutaties,
  maar blokkeren niet het zichtbaar blijven van de te beoordelen artikelen.
- Classificaties (GS1 GPC en CBS ECOICOPv2), artikelgroepen,
  productidentiteiten, synoniemen, kassabonnen, huishouden en voorraad
  blijven afzonderlijke gegevensdomeinen.
- Een identiteitskoppeling is geen aanleiding om een bronbon, voorraad,
  synoniemen of een ander huishouden stilzwijgend te veranderen.

## 4. Implementatievolgorde en acceptatie

**Fase 1 — Artikelidentificatie en Catalogus.** Barcode-scoperegel,
classificatievrije herkenning, bevestigde handmatige opslag, terugwerkend
koppelen van reeds bewaarde barcodes, vervolgens expliciete Lidl-correctie
met gevolgencontrole en vastlegging.

**Fase 2 — Synoniemen en equivalentie.** Centrale directe relaties,
geteste productfamilies, transitive-conflictcontrole en vertrouwde factoren.

**Fase 3 — Voorraad en Bijna op.** Effect op huishoudspecifieke afboeking,
prognose en zichtbaarheid via dezelfde canonieke artikel-ID's.

**Fase 4 — Historisch herstel.** Vooraf gevolgenanalyse, gecontroleerde
verwijzingsreparatie, herberekening van uitsluitend afgeleide resultaten
en bewijs dat de oorspronkelijke aankoopbronnen intact blijven.

Elke fase vereist gerichte, blijvende backendcontracten, household- en
autorisationregressies en, waar toepasselijk, frontend-/ketentests. De
risicoclassificatie bepaalt de verplichte exacte-kandidaat CI-gates.
Geen merge zonder afzonderlijke expliciete PO-GO voor PR en head-SHA;
geen deployment of release zonder afzonderlijke PO-GO.

**Implementatiestatus 12 november 2026:** PR #676 bewaakt preventie
van dubbele huishoudartikelen; PR #677 bevat fase 1-identiteitsfundament
en de expliciete verwerking van bewaarde barcodes. Lidl-correctie en
fasen 2–4 zijn nog niet opgeleverd.


## Aanvullende PO-situatie: discutabele Lidl-artikelen verwijderd uit Catalogus

**PO-melding (12 november 2026):** de PO heeft de Lidl-artikelen met
discutabele barcodes zelf uit de Catalogus verwijderd.

De actuele Inhuis-verwijderroute \`POST /api/catalog/bulk-delete\`
gebruikt **soft-delete** (\`global_products.status = 'deleted'\`).
Daarmee is **niet** aangetoond dat oude \`product_identities\`,
\`external_article_product_links\`, \`ed2_manual_barcodes\`,
huishoudartikelverwijzingen of de oude GTIN definitief afwezig zijn.
De melding betreft een gebruikersactie; in deze PR is de lokale database
niet uitgelezen en zijn de aantallen/verwijderde ID's niet geverifieerd.

Gevolgen voor het ontwerp:

- Een soft-deleted product of diens historische barcodeclaim mag **nooit
  automatisch opnieuw worden geactiveerd of hergebruikt**.
- De bewaarde kassabon-/importbron blijft bestaan. Een onzekere
  identificatie wordt zichtbaar ter beoordeling in Identificeren en
  wordt niet stilzwijgend opnieuw een bewezen globale GTIN.
- Een oude, nog bestaande handmatige barcodebevestiging met een andere
  code wordt niet automatisch vervangen. Dit vereist de reeds ontworpen
  individuele barcodecorrectie met gevolgencontrole, bevoegde bevestiging
  en audit.
- Er is geen reden om de door de PO al soft-deleted Catalogusproducten
  opnieuw te creëren om de uitvoering van fase 1 te hervatten.
- De expliciete bulkactie voor reeds opgeslagen barcodes blijft
  **fail-closed** bij een verwijderde Catalogusidentiteit of nog bestaande
  historische globale claim. Geen automatische databasecleanup,
  migratie of reactivering zonder afzonderlijk veilig bewijs.
