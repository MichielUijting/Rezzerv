# Winkelkoppelingen: duurzame import en onderhoudshervatting

Status: uitvoeringscontract voor de vervolgstap na PR #614; nog **niet**
geïmplementeerd. Risico-indicatie: `TEST_LEVEL_PROVISIONAL: L`.

## Gebruikersbelofte en grens

Een platformbeheerder kan serveronderhoud starten zonder dat reeds door Inhuis
**ontvangen** Lidl- of Jumbo-bonnen verdwijnen. Inhuis verwerkt die ontvangen
bonnen na gecontroleerde vrijgave opnieuw, zonder dat de gebruiker elk exemplaar
weer hoeft aan te bieden. Een bon die alleen in een externe winkelbrowser staat
en nooit aan de Inhuis-server is overgedragen, valt hier niet onder. Die moet zo
nodig opnieuw vanuit de winkel worden aangeboden. Dit mag nooit als 'automatisch
hervat' worden gepresenteerd.

De 38 historische onafgeronde AH-onderhoudsregistraties horen bij een **apart**
hersteltraject. De vijf werkelijk aanwezige AH-bonnen en andere kassabonnen
blijven behouden. Deze queue mag geen historisch bewijs wissen of een oude
onafgeronde onderhoudsregistratie stilzwijgend afsluiten.

## Betrouwbare overdracht

1. Een bevoegd huishouden stuurt een valide bon naar een server-endpoint. Voor
   Jumbo gebeurt dit **uitsluitend na de bestaande handmatige bevestiging**.
   De volledige bevestigde Jumbo-batch wordt in één aanvraag aangeboden, zodat
   een browserafsluiting tussen twee individuele HTTP-aanroepen geen resterende
   bevestigde bonnen doet verdwijnen. Lidl blijft per ontvangen bronbon aanbieden.
2. De server leidt het huishouden zelf af uit de geauthenticeerde context;
   client-supplied household-ID's zijn nooit gezaghebbend. Verificatie van
   provider, bon-ID, formaat, batchlimiet en payloadgrootte gebeurt vóór opslag.
3. De volledige, gesaneerde broninhoud wordt **versleuteld** duurzaam opgeslagen
   met een persistent, onafhankelijk geback-upt sleutelbestand. Een ontbrekende
   of veranderde sleutel leidt tot een zichtbare, geblokkeerde status en nooit
   tot overschrijven of verlies van de wachtrij. Geen bronboninhoud in logs.
4. Eén databasecommit slaat alle gevalideerde bonnen van een bevestigde batch
   atomair op. Een HTTP-bevestiging betekent slechts: **veilig ontvangen**.
   Zij mag niet als 'Kassa verwerkt' worden weergegeven. De client toont
   ontvangst en verwerking afzonderlijk.
5. Een stabiele identiteit (`household_id`, provider, externe bon-ID plus
   bronversie/hash) voorkomt dubbele queue-items bij netwerkherhaling. Een
   gewijzigde inhoud van hetzelfde bonnummer wordt niet stil als identieke
   bon behandeld; de bestaande gecontroleerde refresh-regels blijven gelden.

## Toestand en verwerking

| Toestand | Betekenis | Na herstart |
| --- | --- | --- |
| `pending` | Bevestigd en duurzaam ontvangen, nog niet gestart | Automatisch plannen zodra onderhoud `normal`/`announced` is |
| `processing` | Werk onder een duurzame maintenance-operation, met een identificeerbare bon | Eerst resultaat **reconcilieren**, niet blind aannemen dat niets is gebeurd |
| `completed` | De canonieke receipt-import gaf een bewezen resultaat | Geen herimport |
| `review_required` | Uitkomst onzeker, inhoud ongeldig of sleutel ontbreekt | Niet automatisch herhalen; beheerder ziet reden en bewijs |

De werknemer claimt maximaal één bon atomair, controleert maintenance-admission
en begint geen nieuwe bon in `draining`, `locked`, `verifying` of `blocked`.
Een normale stop laat de huidige bon afronden, registreert de uitkomst en stopt
vóór de volgende. Een queue-item in `pending` telt **niet** als lopende
maintenance-operation en mag het stilleggen dus niet blokkeren.

Bij een abrupte stop kan een verwerking precies tussen bestandsschrijf en
databasecommit eindigen. De herstart controleert dan eerst de feitelijke
canonieke `raw_receipt`/receipt-source-identiteit, opgeslagen inhoudsidentiteit,
eventuele voorlopige bestanden en overige domein-effecten. Een oud
`maintenance_operations`-record mag pas na dat concrete bewijs via de
geautoriseerde onderhoudsherstelprocedure worden afgesloten. Onbesliste
gevallen blijven `review_required`; een tijdslimiet is geen bewijs.

Een geslaagde, geverifieerde onderhoudsvrijgave wekt de scheduler zonder
browserinteractie; een Windows-herstart start dezelfde persistent ingestelde
Inhuis-service en diens queue-scanner, maar **ontgrendelt onderhoud niet**.
Er wordt nooit een parallelle tweede worker voor dezelfde bon gestart.

## API en gebruikersweergave

- Nieuwe queue-ingang voor een volledige bevestigde Jumbo-batch en voor losse
  Lidl-bonnen; de bestaande synchrone `/api/receipts/retailers/import` behoudt
  compatibiliteit zolang afnemers die nog gebruiken.
- Huishoudgebonden leesroute voor `pending`, `processing`, `completed` en
  `review_required`, inclusief aantallen en daadwerkelijke voltooiing.
- Platformbeheer toont lopende winkelimports afzonderlijk van ingelogde
  gebruikerssessies en vermeldt veilig geparkeerde queue-items apart.
- `Onderhoud starten` wacht alleen op werkelijk actieve importbewerkingen;
  `hervatten` start pas na de bestaande geverifieerde vrijgave. Een beheerdersactie
  om een onbewezen import als gereed te markeren is niet toegestaan.
- De Jumbo/Lidl-interface mag bij een HTTP-timeout niet opnieuw aannemen dat
  geen opslag plaatsvond. Eerst status/idempotentiesleutel navragen.

## Migratie, back-up en terugval

- Alembic maakt een nieuwe household-scoped queue-tabel met constraints,
  unieke idempotentiesleutel, status-/tijdvelden en encrypted payload.
  De bestaande PostgreSQL-onderhouds-write-barrier geldt eveneens voor deze tabel.
- Voor productie-activatie: verifieer een onafhankelijk herstelbare back-up van
  database **en encryptiesleutel**, de schemahead en het rollbackpad. Een
  nieuwe backend met oude schemahead faalt gesloten.
- Geen automatische opschoning van in-flight of historische queue-items en
  geen destructieve downgrade als er onafgerond werk of payloads aanwezig zijn.
- Er vindt geen stille omschakeling van de huidige vijf AH-bonnen plaats;
  eventuele AH-aansluiting op hetzelfde queuecontract is een aparte stap.

## Vereiste acceptatieproeven

1. Jumbo: tien expliciet bevestigde bonnen worden atomair geparkeerd; browser
   sluiten na ontvangst; na serverherstart worden alle tien exact eenmaal
   functioneel verwerkt.
2. Lidl: ontvangen bon blijft bewaard na browserafsluiting en komt na vrijgave
   alsnog in Kassa; niet-aangeboden bronbon wordt niet fictief aangemaakt.
3. Herhaalde HTTP-aanvraag of workerclaim veroorzaakt geen dubbele bon of
   voorraadmutatie; gewijzigde bronversie krijgt de juiste controleprocedure.
4. `draining` tijdens een batch laat de lopende bon veilig aflopen, parkeert de
   rest; bij `locked` is er geen nieuwe importactiviteit.
5. Abrupte stop vóór/na opslag, tijdens canonieke ingest en vóór resultaat-
   registratie wordt met geïsoleerde PostgreSQL- en bestandstests geïnjecteerd.
   Ambigue side-effects blokkeren automatische herhaling.
6. Huishouden A kan geen queue, payload of status van B lezen, wijzigen of
   laten importeren; ontbrekende rechten blijven 401/403 volgens autorisatie.
7. Ontbrekende decryptiesleutel, ontbrekende migratie, gewijzigde schemahead,
   mislukte back-up en niet-gereconcilieerde historische registraties stoppen
   de relevante overgang aantoonbaar veilig.
8. Officiële risiconiveau-L-gates inclusief exacte F7 Full Regression slagen
   op definitieve kandidaat-SHA, gevolgd door functionele PO-acceptatie.

## Implementatievolgorde

1. Schema + versleutelde queue + idempotentie- en isolatiecontracttests.
2. Onderhoudsbewuste worker + crashreconciliatie + startup/shutdown-tests.
3. Jumbo-batch- en Lidl-overdracht, statusweergave en bestaande contracttests.
4. Geïsoleerde PostgreSQL-/serverherstartproef en PO-acceptatie; geen deployment
   zonder afzonderlijke expliciete PO-toestemming.
