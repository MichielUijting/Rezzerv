# PO Acceptance Pack — F8-PO-01

Dit is de vaste korte PO-check voor de releasecandidate. Het doel is **niet** om regressietests opnieuw handmatig uit te voeren. De technische bewijzen zijn al eigendom van de geautomatiseerde testauthorities. De PO beoordeelt uitsluitend of het product begrijpelijk is, logisch aanvoelt, duidelijke feedback geeft en het bedoelde productgedrag zichtbaar maakt.

## Uitgangspunten

- Voer deze check uit op de releasecandidate die in Phase 9 wordt beoordeeld.
- De volledige check duurt ongeveer **25 minuten**.
- Gebruik normale gebruikershandelingen; inspecteer geen interne technische bewijzen.
- Een journey is alleen `accepted` wanneer alle criteria vanuit gebruikersperspectief overtuigend zijn.
- Een onduidelijkheid die releaseblokkerend is, maakt de journey `rejected` en wordt als blocking finding vastgelegd.
- Het resultaat wordt vastgelegd op basis van `po_acceptance_result.template.json` en aan de exacte candidate-SHA gekoppeld.

## PO-01 — First use, onboarding and settings · 6 min

**Doel:** beoordelen of een nieuw huishouden zonder product- of implementatiekennis begrijpelijk kan starten en de gekozen configuratie later kan herkennen en aanpassen.

1. Open het product als nieuwe gebruiker, registreer en log in.
2. Rond onboarding voor één huishouden af en kies de locatie-instelling die bij het testhuishouden past.
3. Open vanuit Home de instellingen en wijzig de locatie-instelling één keer.
4. Ga terug naar de normale gebruikersflow en beoordeel of navigatie en zichtbare keuzes logisch meebewegen.
5. Log uit en opnieuw in en controleer of actief huishouden en configuratie nog steeds duidelijk zijn.

**Acceptatie:**

- de volgende logische actie is steeds duidelijk;
- labels en toelichting zijn begrijpelijk zonder technische voorkennis;
- de locatie-instelling heeft een zichtbaar en consistent producteffect;
- opnieuw inloggen veroorzaakt geen twijfel over huishouden of configuratie.

Dekt: `P0-ACCOUNT-SESSION`, `P0-ONBOARDING`, `P0-SETTINGS-PROJECTION`, `P0-LOCATIONS-POLICY`.

## PO-02 — Household collaboration and permission boundaries · 5 min

**Doel:** beoordelen of uitnodigingen, huishoudcontext en rolgrenzen voor normale gebruikers begrijpelijk zijn.

1. Nodig als huishoudbeheerder een tweede gebruiker uit.
2. Accepteer als tweede gebruiker de uitnodiging en open het huishouden.
3. Wissel van huishoudcontext wanneer meerdere huishoudens beschikbaar zijn en beoordeel of de actieve context duidelijk is.
4. Probeer als niet-beheerder één huishoudinstelling die bewust beperkt is.
5. Ga terug naar normaal gebruik en beoordeel of beperking en rol begrijpelijk blijven.

**Acceptatie:**

- uitnodiging en acceptatie maken de relatie gebruiker ↔ huishouden duidelijk;
- het actieve huishouden is ondubbelzinnig;
- een verboden actie levert een begrijpelijke productreactie op;
- niets in de interface suggereert toegang tot data of rechten van een ander huishouden.

Dekt: `P0-HOUSEHOLD-MEMBERSHIP`, `P0-AUTHORIZATION-ISOLATION`.

## PO-03 — Receipt to stock and almost-out journey · 10 min

**Doel:** beoordelen of de kernbelofte van het product als één samenhangende gebruikersreis voelt, zonder technische edge-cases opnieuw te testen.

1. Upload één normale ondersteunde kassabon en beoordeel hem in Kassa.
2. Keur de bon goed en ga voor een kleine representatieve selectie door naar Uitpakken.
3. Maak de keuzes die een normale gebruiker zou maken en rond Uitpakken voor die artikelen af.
4. Open Voorraad en bekijk voor één verwerkt artikel voorraad en zichtbare historie.
5. Boek één normale consumptie zodat het artikel relevant wordt voor Bijna op en open daarna Bijna op.
6. Open twee verschillende artikeldetails, hernoem één artikel en beoordeel of het andere artikel in detail en historie duidelijk een zelfstandig artikel blijft.

**Acceptatie:**

- Kassa, Uitpakken, Voorraad en Bijna op voelen als één logische keten;
- de gebruiker begrijpt wat is geaccepteerd, verwerkt en gewijzigd;
- voorraad- en bijna-opgedrag is vanuit de handelingen begrijpelijk;
- detail en historie blijven herkenbaar gekoppeld aan het gekozen artikel, ook na hernoemen;
- interne termen of identifiers zijn niet nodig om de flow te begrijpen.

Dekt: `P0-RECEIPT-INVENTORY-ALMOSTOUT`, `P0-KASSA-REVIEW`, `P0-UNPACKING`, `P0-INVENTORY`, `P0-ALMOST-OUT`, `P0-ARTICLE-IDENTITY`.

## PO-04 — Platform administration without household privilege confusion · 4 min

**Doel:** beoordelen of platformbeheer als afzonderlijke autoriteitscontext duidelijk en veilig wordt gepresenteerd.

1. Open platformbeheer met een rol die hiervoor bevoegd is.
2. Bekijk de beschikbare beheerfuncties en de manier waarop platformcontext zichtbaar wordt gemaakt.
3. Voer één veilige toegestane beheeractie uit die in de testomgeving beschikbaar is.
4. Ga terug naar huishoudcontext en beoordeel of platformrechten nergens als huishoudlidmaatschap of huishoudbeheer worden gepresenteerd.

**Acceptatie:**

- platformcontext is duidelijk anders dan normaal huishoudgebruik;
- beschikbare en niet-beschikbare acties passen bij de rol;
- de interface suggereert niet dat een platformrol automatisch huishoudrechten geeft;
- de beheeractie geeft duidelijke productfeedback.

Dekt: `P0-PLATFORM-AUTHORITY`.

## Wat de PO nadrukkelijk niet hoeft te doen

De PO hoeft geen migraties, database-eindstaten, API-responses, retry-mechanismen, idempotentievarianten, foutinjecties, buildlogs of CI-runs handmatig te reproduceren. Die kwaliteit is al afgedekt door de technische Release Acceptance authorities. `P0-MIGRATION-STARTUP` is daarom bewust geen PO-journey.

## Resultaat

Na uitvoering krijgt elke journey uitsluitend `accepted` of `rejected`. Het totale resultaat is alleen `accepted` wanneer alle vier journeys zijn geaccepteerd en er geen blocking findings zijn. Tot dat moment blijft `F7-REL-02` open en blijft de centrale Release Acceptance-status `partial`.
