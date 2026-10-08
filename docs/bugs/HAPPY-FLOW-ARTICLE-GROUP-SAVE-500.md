# Happy-flow foutcorrectie: artikelgroep opslaan geeft HTTP 500

Status: reproduceerbare gebruikersmelding, oorzaak nog te bevestigen. Dit is een werkdocument bij de afzonderlijke Draft-PR; **geen bewijs van een gerepareerde fout**.

## Feitelijke gebruikersobservatie (8 oktober 2026)

Tijdens lokale functionele happy-flow-tests van Inhuis, zowel op mobiele als desktopweergave:
1. Open een scherm waarin een artikelgroep kan worden toegevoegd.
2. Maak een nieuwe artikelgroep aan.
3. Kies **Opslaan**.
4. Resultaat: de applicatie meldt **Interne serverfout**.

De aangeleverde schermafbeelding toont de mobiele kassabon-/Uitpakken-detailweergave `http://localhost:5174/kassabonnen/...`, met artikelregels en o.a. de artikelgroepselectie `Niet ingedeeld`. De afbeelding toont **niet** de stacktrace, netwerkresponse of exacte mutatieroute; leg daarom geen speculatieve root cause vast.

## Scope

Deze PR dient uitsluitend de foutcorrectie van **artikelgroep toevoegen/opslaan** voor de bestaande mobiel- en desktopflow. Geen andere functionaliteit, permissies, data, pagina-indeling of performancewerk toevoegen.

## Benodigde objectieve diagnose

- Vind de concrete frontendactie en backend-API-route voor het toevoegen van een artikelgroep, inclusief de gedeelde service-/databaseaanroep.
- Reproduceer met exact dezelfde API-payload, de actuele PostgreSQL-schema-/Alembic-versie en een geautoriseerde testgebruiker.
- Inspecteer de backendlogs en HTTP-response op het moment van opslaan; identificeer de *daadwerkelijke* exception en oorzaak, niet alleen de HTTP 500-melding.
- Controleer vervolgens of de fout beide viewports betreft, of één gedeelde opslagroute, en of opslag eventueel ondanks de fout gedeeltelijk is uitgevoerd.
- Behoud alle bestaande huishoudisolatie, autorisatie, canonieke product-/artikelgroepidentiteit en transactieveiligheid.
- Los alleen de bewezen oorzaak op; geen datareparatie of migratie op aanname.

## Vereiste regressie / acceptatie

- Geldige artikelgroep wordt aangemaakt en na herladen zichtbaar in de juiste context.
- Mobiele en desktopgebruikers doorlopen dezelfde succesvolle opslagroute.
- Ongeldige/lege/dubbele invoer geeft de contractuele foutstatus/validatiemelding, **geen HTTP 500**.
- Geen dubbele records bij opnieuw opslaan of netwerkfout; geen gedeeltelijke mutaties.
- Andere huishoudens kunnen de nieuwe artikelgroep niet onbedoeld lezen, wijzigen of koppelen; autorisatie blijft gehandhaafd.
- Eventueel geraakte bon-/artikelregels blijven ongewijzigd totdat de gebruiker expliciet koppelt.
- Voeg een gerichte foutreproducerende backendtest toe en voer die na reparatie groen uit; vervolgens de toepasselijke normale/CI-gates.

## PO-acceptatie

Functionele hertest in de bestaande lokale Inhuis-opstart (`start.bat`): voeg een artikelgroep toe vanuit de oorspronkelijke happy flow in de mobiele én desktopweergave; controleer dat opslaan slaagt en het resultaat na verversen blijft staan.

## Afbakening en status

Nog **niet** gerepareerd of lokaal gereproduceerd met serverlogs. Zonder concrete foutdetails kan de oorzaak niet als vastgesteld worden beschouwd. De PR blijft Draft tot fix, gerichte tests, versie-/CI-controles en PO-hertest rond zijn.

TEST_LEVEL_PROVISIONAL: M — voor de uiteindelijke foutcorrectie; herclassificeer fail-closed wanneer de werkelijk geraakte paden hoger risico hebben.

STYLEGUIDE_IMPACT: reviewed-no-change — dit onderzoek wijzigt geen UI-weergavecontract.
