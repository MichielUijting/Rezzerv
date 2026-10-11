# AH-klantkaartkoppeling — afronding en acceptatie (10 oktober 2026)

Status per 11 oktober 2026: gedeeltelijke implementatie en lokale PO-acceptatie van de AH-synchronisatiemelding. Onderstaande restpunten zijn expliciet overgedragen; geen volledige functionele acceptatie of mergegereedheid.
Voorlopig risico: **L**, wegens authenticatie, financiële kassabonverwerking, huishoudisolatie en ontvangstketen.

## Af te ronden functionele eisen
1. Bij openen van Kassa worden voor een gekoppeld huishouden uitsluitend nieuwe AH-bonnen opgehaald, zonder dubbele opslag.
2. De handmatige actie **Nu synchroniseren** werkt en geeft resultaat en eventuele fouten begrijpelijk weer.
3. Datum, winkel, artikelregels, aantallen, eenheidsprijzen en bonbedragen worden met de AH-bron gereconcilieerd.
4. Een tweede sync na succesvolle eerste sync importeert nul doublures; gedeeltelijke uitval is veilig herhaalbaar.
5. Accounttokens blijven versleuteld, buiten logs/UI en gebonden aan het juiste huishouden; herstart behoudt koppeling.
6. AH-inloggen verloopt via browser en automatische callback, zonder autorisatiecode te kopiëren.
7. Diagnoseer de historische uitkomst **99 van 100** zonder te veronderstellen dat de 100e ontbreekt: onderscheid *reeds bekend*, *buiten limiet*, *detailfout* en *importfout*. Houd bon-ID's en accountgegevens buiten publieke rapportage.
8. Tijdens sync is begrijpelijke voortgang zichtbaar (aantal gevonden, verwerkt, overgeslagen en mislukt). Fout betekent nooit stilzwijgend succes.
9. Test de UAC-vrije `ah-login.127-0-0-1.sslip.io`-route op geen beheerdersprompt, werkende hCaptcha, automatische terugkeer en zichtbare bonnen in Kassa.
10. Vergelijk AH-kortingen, bon- en regeltotalen en betalingen; kortingen of betaalmiddelen worden nooit fysieke voorraad.

## Voorlopige technische bevindingen uit main
- `backend/app/integrations/retailer_accounts/ah.py` leest standaard maximaal 100 bonoverzichten via één API-page; pagination en paginabeperking verdienen controle.
- `backend/app/services/ah_receipt_sync_service.py` kent per-bon foutverzameling en bewaart geslaagde receipt IDs als bekend; de actuele oorzaak van 99/100 is hiermee nog **niet** bewezen.
- AH is een ongedocumenteerde externe API; netwerk-, account- en captcha-afhankelijkheden kunnen lokaal functioneel bewijs vereisen.
- De handoff van gemergede PR #555 staat in `docs/project/PR555-AH-OAUTH-HANDOFF.md`.

## Veiligheid / scope
- Geen wijzigingen aan gebruikersdata, secrets, bestaande volumes of hosts-bestand op basis van aannames.
- Bestaande account-/huishoud- en ontvangstcontracten blijven leidend; geen parser- of databasearchitectuur-refactor zonder bewezen noodzaak.
- Testen met gesynthetiseerde financiële bonnen, geen echte klant-/kassabondata naar GitHub.
- Gewone lokale PO-test: bewezen veilig scriptpatroon; schone werkmap, non-destructieve fast-forward en exacte kandidaat-SHA; daarna de bestaande `start.bat`.

## Verificatie en oplevering
- Eerst gerichte diagnose en contracttests; vervolgens implementatie, frontend build en relevante ontvangst-/security-/ketenchecks.
- Finale patchversie + versiesync pas als de code definitief is; F7/exact-candidate uitsluitend op finale SHA.
- PR blijft Draft tot vereiste checks en functionele acceptatie kloppen. Merge alleen na expliciete PO-GO voor exacte SHA; release afzonderlijk.

## Overdracht bij afsluitvoorbereiding PR #571 — 11 oktober 2026

Deze paragraaf is de leidende **voortgangs- en restpuntenoverdracht**, niet een verklaring dat alle tien acceptatiecriteria zijn gehaald. Bewaar bij latere hervatting zowel de oorspronkelijke eisen hierboven als deze feitelijke stand. Vervolgwerk wordt alleen als uitgevoerd aangemerkt na nieuw bewijs.

### Wat al is aangetoond of geïmplementeerd

- De PO heeft lokaal bevestigd dat de handmatige AH-synchronisatie werkt en dat de synchronisatiemelding verdwijnt zodra de pagina Winkelkoppelingen wordt verlaten (11 oktober 2026). Dat laatste is expliciet door de PO geaccepteerd.
- De synchronisatie toont aantallen gevonden, verwerkt, al bekend en mislukt, plus veilige foutfase, fouttype, validatiereden en structuurinformatie. Een late respons na het verlaten van de pagina mag de melding niet opnieuw tonen.
- Het concrete praktijkresultaat was **100 gevonden, 0 nieuw verwerkt, 99 al bekend en 1 mislukt**. De resterende bon faalt in de Kassa-import met `ValueError` / *geen artikelregels beschikbaar*. De diagnose meldt `products=null`, 0 ruwe en 0 herkende artikelregels, geen bekende alternatieve artikelvelden, 0 kortingen en 1 betaling. Dit bewijst dat de huidige AH-detailquery voor die transactie geen productlijst leverde; het bewijst **niet** dat de daadwerkelijke transactie geen artikelen had.
- De koppeling geeft voor een mislukte bon ook de AH-overzichtsdatum/-tijd door, waar beschikbaar. De transactiesoort is in het huidige AH-contract **niet beschikbaar**. De PO heeft de daadwerkelijke datum/tijd nog niet teruggekoppeld; deze zijn dus onbekend in dit document.
- De sync-implementatie bewaart geslaagde externe bon-ID's als bekend en laat een mislukte bon opnieuw proberen. Hiervoor bestaan synthetische tests; dit is geen volledige productie-/huishoudisolatieproef.
- Volgens de lokale PO-test bleef de AH-koppeling na herstart aanwezig. Dat vervangt geen formele encryptie-, privacy- of huishoudisolatietest.

### Functionele restpunten, met hervatcriteria

| Oorspronkelijke eis | Stand | Vervolg en bewijs voor afronding |
| --- | --- | --- |
| 1. Automatisch synchroniseren bij openen Kassa | **Open / niet end-to-end bewezen** | Controleer of en wanneer Kassa automatisch alleen onbekende AH-bonnen ophaalt. Borg autorisatie, foutafhandeling, geen onnodige herhaalde oproepen en geen duplicaten; voeg gerichte integratie-/UI-tests toe. |
| 2. Handmatige sync met begrijpelijke fouten | **Lokaal functioneel aanvaard, technische gates nog open** | Behoud de werkende melding, inclusief verdwijnen bij paginaverlaten; regressie op late async-respons en niet-AH-feedback. |
| 3. AH-bonvelden en bedragsovereenkomst | **Open / gedeeltelijk werkend** | Vergelijk aankoopdatum/-tijd, winkel, regels, aantallen en eenheidsprijzen met de originele AH-bon; geen stille aannames over ontbrekende waarden. |
| 4. Idempotentie en herhaalbare fouten | **Deels via code en synthetische tests** | Bewijs onder PostgreSQL/huishoudisolatie dat tweede sync geen doublures oplevert en dat een gedeeltelijke fout veilig opnieuw wordt geprobeerd. |
| 5. Tokenbeveiliging en herstart | **Lokaal behoud koppeling waargenomen, formeel open** | Herhaal encryptie-, sessie-, logprivacy-, huishoudenwissel- en herstarttests; geen secrets in artefacten. |
| 6. Browserlogin en automatische callback | **Historisch werkend, nog niet volledig opnieuw geaccepteerd** | Test opnieuw zonder handmatig code overnemen, met correcte callback en veilige sessieverwerking. |
| 7. Historische 99/100-afwijking | **Oorzaak technisch ingeperkt, nog open** | Identificeer transactie via datum/tijd in de AH-app; bepaal of het een bijzondere betaling of onvolledige API-bondetails betreft. Onderzoek ook expliciet grens van eerste 100/paginering. Bij werkelijk ontbrekende gegevens blijft de bon herhaalbaar en wordt geen fictieve artikelregel/voorraad aangemaakt. |
| 8. Voortgang en expliciete foutstatus | **Lokaal functioneel bewezen** | Behoud teller- en foutweergave, en controleer deze in de finale UI-regressie. |
| 9. UAC-vrije loginroute | **Open / niet integraal bewezen** | Test de bestaande `ah-login.127-0-0-1.sslip.io`-route op geen beheerdersprompt, hCaptcha, callback, succesvolle sessie en zichtbare bonnen in Kassa. |
| 10. Kortingen, betalingen, regeltotalen | **Open** | Eerdere PO-vergelijking toonde afwijkende bonbedragen en niet/verkeerd toegepaste kortingen. Reconcilieer AH-bron en Kassa met gesynthetiseerde voorbeelden; geen kortingen/betalingen naar fysieke voorraad. |

### Beslissingen / afbakening voor de volgende werksessie

1. De PO heeft expliciet de geldverschillen tijdelijk **geparkeerd** om eerst de ene mislukte bon te diagnosticeren. Dit is **geen afkeuring of schrapping** van eisen 3 en 10: ze blijven formeel open.
2. Niet de 100e bon als succesvol registreren enkel om de teller sluitend te maken. Geen fictieve voorraadregels, geen terugzetten van data, geen verlies van retrybaarheid.
3. De `posReceiptDetails`-query kan `products=null` teruggeven terwijl een betalingsregel aanwezig is. Zonder aanvullende broninformatie is het transactietype niet bewezen. Onderzoek gericht maar presenteer geen hypothese als feit.
4. De AH-overzichtsquery leest momenteel één pagina met maximaal 100 bonnen; **100 gevonden** bewijst niet dat er totaal precies 100 bonnen bestaan. Beoordeel pagina-omslag en limiet in vervolgwerk.
5. Gebruik geen uitvoerbare diagnosescripts met tijdelijke gegenereerde Python-code: Norton blokkeerde zo'n bestand bij de PO. Hergebruik liever de ingebouwde, privacyveilige app-diagnose.
6. Er trad lokaal meermaals een ogenschijnlijk hangende `start.bat` op tijdens `docker compose up -d`; na de handmatige Ctrl+C stonden PostgreSQL, backend en frontend in de logs uiteindelijk draaiend. **Geen objectief vastgestelde startupoorzaak**, dus geen automatische aanpassing van timeouts, poorten, Compose of volumes. Dit is afzonderlijk operationeel onderzoek buiten de AH-functionele acceptatie.

### Open kwaliteits- en releasevoorwaarden

- PR #571 is tijdens deze overdracht nog **Draft**; de laatst gecontroleerde candidate vóór deze documentatieaanvulling was `99ef4c774b78fab9828c3914a6e19eee0926a32b`. Documentatiecommits veranderen de head-SHA: gebruik bij hervatting altijd de actuele GitHub-SHA.
- Op die kandidaat waren 15 checks succesvol, één (*Validate canonical Inhuis styleguide*) gefaald en één (*Full Regression candidate decision*) overgeslagen. **Geen claim van finale gate-groen**; onderzoek eerst concreet de rode styleguide-job en voer daarna de relevante checks op de actuele kandidaat uit.
- De volledige PR-delta heeft voorlopig risico **L**. Zodra de uiteindelijke runtime-scope definitief is: vereiste patchversie/versiesync, gerichte tests, normale/preflight-gates, daarna Ready en de verplichte F7 Full exact-candidate volgens repositorybeleid. Elk nieuw SHA maakt eerder exact-candidate-bewijs ongeldig.
- Als de PO besluit de resterende functionele eisen na deze PR op te pakken, neem ze expliciet over in een **afzonderlijke vervolg-PR of issues**, met traceerbare verwijzing naar dit document. Noem de huidige PR dan een **gedeeltelijke afronding**; beweer niet dat eisen 1-10 functioneel klaar zijn. Afzonderlijk vastgelegde eisen mogen niet ongemerkt verdwijnen uit de acceptatiebaseline.
- **Geen merge zonder afzonderlijke expliciete PO-GO voor de exacte kandidaat-SHA**. Release/deployment vergt een andere expliciete PO-GO.

### Herstartinstructie voor het vervolg

Begin met actuele `main`, PR/branch/SHA en repositoryregels; lees dit overdrachtsdocument en `docs/project/PR555-AH-OAUTH-HANDOFF.md`. Bepaal met de PO eerst welke open eis de nieuwe taak vormt. Verzamel privacyveilige bronfeiten, test een gerichte reparatie, bescherm database/runtime en herhaal pas daarna de verplichte PR-gates. 
