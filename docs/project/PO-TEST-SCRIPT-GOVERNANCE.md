# Canonieke Inhuis PO-testscriptroute (Draft)

TEST_LEVEL_PROVISIONAL: L
Reden: deze taak wijzigt CI/testinfrastructuur en lokale uitvoerbare PO-testscripts.

## Bron en herkomst

De PO leverde op 12 oktober 2026 het werkelijk eerder gebruikte bestand
Inhuis_PR544_Lidl_ontbrekende_artikelen_test(2).bat aan.

- Origineel: 250 regels.
- Oorspronkelijke SHA-256:
  8cc2cc5242c46347ae0005eb4b89c8ce8e3eea90cc837772c93ce4b087a76b5e
- Historische branch: codex/lidl-plus-receipt-sync.
- Historische SHA in het script: ee297e937ed5b8ce20763f8e745edf75fb7569d2.
- Herkomst: https://github.com/MichielUijting/Rezzerv/pull/544
- Vastgelegde standaard: docs/project/LOCAL-PO-TEST-STARTUP-STANDARD.md (PR574).

De oorspronkelijke bytes zijn niet ongewijzigd naar de openbare repository
gekopieerd omdat zij een persoonsgebonden absoluut Windows-pad bevatten.
De SHA-256 legt de geinspecteerde bron vast. Het nieuwe sjabloon onder
scripts/po-tests/po-test-template.bat is een herleidbaar afgeleid bestand,
niet een byte-identieke kopie.

## Gerechtvaardigde verschillen ten opzichte van PR544

1. Repositorypad via USERPROFILE in plaats van een persoonsspecifiek pad.
2. Branch/SHA/titel/testscenario's als verplichte generator-invoervelden.
3. Git-status en staged/tracked wijzigingen expliciet fail-closed controleren.
4. Niet-gevolgde standalone-/buildbestanden intact laten en Git zelf
   doelbranchconflicten laten weigeren.
5. Remote head-SHA na gerichte fetch en lokale HEAD na branchwissel controleren.
6. Repo-herkomst en officiele start.bat toetsen; geen eigen Docker-orchestratie.
7. Een beknopt rapport in Downloads schrijven.
8. PR544-specifieke testinstructies vervangen door nieuwe PO-testscenario's.

Historisch werkend is niet gelijk aan volledig conform de latere PR574-regels.
Dit zijn bewuste veiligheidswijzigingen, geen stilzwijgende herschrijving.

## Officiele opleverroute

1. Generator generate_po_test.py produceert uitsluitend vanuit het sjabloon.
   Ontbrekende bron betekent STOP zonder output.
2. Veiligheids-/negatieve tests en Windows-integratietests gebruiken een
   wegwerp-Git-repository met een onschadelijke start.bat.
3. Na merge kan een workflow_dispatch op de default branch worden uitgevoerd
   met PR-nummer, actuele branch/SHA, titel en testinstructies.
   Als alternatief kan de repository-eigenaar via een PR-commentaar een
   gecontroleerde uitgifte aanvragen zonder handmatige GitHub-formuliervelden.
4. Live PR-data wordt gecontroleerd tegen de opgegeven branch en SHA.
   Alleen bij geslaagde Windows-tests wordt een batch + JSON-bewijs geupload.
5. Bewijs bevat artifact-hash, kandidaat-SHA, generator-commit en workflow-run-ID.

Voor de PO blijft het uiteindelijk een eenvoudig uitvoerbaar BAT-bestand.

## Eindbestand als kwaliteitsautoriteit (versterking oktober 2026)

De oorzaak van de dubbele `echo echo` was dat het sjabloon zelf al een
`echo` rond de placeholder zette, terwijl de generator iedere instructie
ook als `echo` renderde. De uitvoer kon daardoor syntactisch geldig zijn
en toch onjuist aan de PO worden gepresenteerd.

De generator voert nu een **byte-voor-byte vergelijking** uit van het
eindbestand met opnieuw gegenereerde canonieke uitvoer, inclusief:
- geldige CRLF-regelafbreking en ASCII;
- geen dubbele `echo echo` of achtergebleven placeholders;
- exact de bedoelde kandidaatbranch en SHA in de gegenereerde uitvoer;
- precies één officiele `start.bat`-aanroep.

De bestaande Windows-workflow roept na generatie een afzonderlijke
`--verify-only`-controle op hetzelfde artefact aan, vóór hash/evidence/upload.
Een fout is fail-closed: er verschijnt dan **geen gevalideerd downloadartefact**.
De negatieve tests muteren opzettelijk het gegenereerde bestand (dubbele echo,
verkeerde SHA, aangepaste start, kapotte CRLF) en vereisen afwijzing.

**Distributieregel:** lever uitsluitend een via
`Canonical PO test script validation and delivery` / `workflow_dispatch`
of de door de repository-eigenaar gevraagde `issue_comment`-uitgifteroute
gepubliceerd artefact met het corresponderende `evidence.json` uit.
Een handgemaakt chatbestand zonder dit actuele uitgiftebewijs mag niet als
officieel getest PO-script worden aangeboden. Controleer vlak voor aanbieding
dat de PR-head nog overeenkomt met het bewijs. De GitHub-ruleset beschermt
repositorywijzigingen; hij kan technisch niet verhinderen dat iemand buiten
GitHub om een onbewezen bestand maakt. Die grens blijft expliciet.

## Nog niet aangetoonde onafhankelijke borging

- GitHub ruleset, verplichte checkstatus, reviewtoegang en bypassrechten
  waren met de beschikbare toegang niet objectief uitleesbaar.
  Tot verificatie is onafhankelijke afdwinging NIET BEWEZEN.
- ChatGPT kan rechtstreeks een los downloadbestand genereren; dat wordt door
  GitHub niet automatisch tegengehouden. Zo'n bestand mag niet als officieel
  gevalideerd worden gepresenteerd.
- Een geslaagde geisoleerde Windows-test is geen bewijs dat de echte Docker-
  of PostgreSQL-opstart op de computer van de PO geslaagd is.
- De originele bronhash bewijst byte-identiteit met de upload, niet dat iedere
  historische lokale test exact met deze bestandsbytes is uitgevoerd.
- Geen merge zonder expliciete PO-GO. Release/deployment vereisen eigen GO.

## Acceptatievoorwaarden

- [ ] Windows-unit-, negatieve en integratietests groen.
- [ ] F7 Full Regression (L) groen op definitieve SHA.
- [ ] Officieel artifact en evidence na merge aantoonbaar geproduceerd.
- [ ] Ruleset, bypass en reviewbescherming objectief geverifieerd.
- [ ] Aangetoond dat verboden wijzigingen door verplichte gate worden geblokkeerd.

## Uitgifte zonder PO-handwerk (PR-commentaar)

De Github-koppeling van ChatGPT kan wel een GitHub PR-commentaar plaatsen,
maar geen `workflow_dispatch` aanroepen. De officiële workflow ondersteunt
daarom ook een verzoek via een commentaar door de repository-eigenaar:

```text
/inhuis-po-test <exacte 40-tekens kandidaat-SHA>
Controleer Lidl importperiode
Controleer een bestaande en een herimporteerde bon in Kassa
```

- Alleen een commentaar op een bestaande PR, afkomstig van de eigenaar van
  de repository, mag het script vrijgeven; andere reacties worden genegeerd
  of fail-closed afgewezen.
- Het script wordt met `contents: read` en `pull-requests: read` op de
  vertrouwde default-branch gegenereerd. Er zijn geen repository secrets of
  verhoogde GitHub-schrijfrechten nodig.
- De branch wordt uitsluitend van de actuele PR-head gelezen en moet een
  geldige `codex/`-branch zijn. De SHA in het commentaar moet exact gelijk
  zijn aan de actuele PR-head; een gewijzigde kandidaat wordt afgewezen.
- Het standaard Windows-veiligheidspakket, canonieke generator, byte-identieke
  `--verify-only` en SHA-256-bewijs gelden ongewijzigd.
- De workflow publiceert alleen de BAT met `evidence.json` als artefact.
  De PO hoeft hiervoor zelf geen GitHub Actions-formulier in te vullen.
- Als GitHub deze nieuwe trigger niet start (bijvoorbeeld door de
  identiteit van de commentaarauteur), blijft de bestaande
  `workflow_dispatch`-route beschikbaar; er is geen toestemming tot het
  uitschakelen van controles of omzeilen van gates.

De repositorycode kan de mogelijkheden van een ChatGPT-connector niet
wijzigen. Deze route gebruikt alleen reeds beschikbare GitHub-acties.
