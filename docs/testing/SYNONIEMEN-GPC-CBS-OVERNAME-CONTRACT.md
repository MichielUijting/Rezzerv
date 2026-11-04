# PR — automatische GPC/CBS-overname bij bevestigde artikelsynoniemen

**TEST_LEVEL_PROVISIONAL: L.** Functionele wijziging in de centrale Catalogusautoriteit, transacties en synoniemketen. **Geen migratie**: bestaande classificatietabellen en CBS-historie blijven de gezaghebbende opslag.

## Contract

- Het bestaande, door Superuser/Frontteam beveiligde synoniemen-bevestigingsendpoint `POST /api/external-databases/article-synonyms/link` blijft de enige trigger voor deze eerste implementatie.
- Bevestigen van een expliciet voorgesteld paar autoriseert het automatisch overnemen van **ontbrekende** officiële GPC- en CBS-indelingen. Een keten van bevestigde relaties vormt voor deze classificatieovername een groep; artikelidentiteiten, huishoudartikelen, voorraad en bonnen worden niet samengevoegd.
- De gehele batch (relaties, GPC, CBS en CBS-historie) wordt binnen **één** bestaande `engine.begin()`-transactie opgeslagen. Een PostgreSQL-transaction advisory lock voorkomt dat parallelle synoniembevestigingen tegen een verouderde groep rekenen.
- **GPC:** bij een eenduidig aanwezige Brick worden alleen ontbrekende `global_product_gpc_bricks`-rijen aangevuld. `assignment_source='synonym_inherited'` en `migrated_from='synonym:<bronproduct-id>'` documenteren de herkomst. Geen nieuw GPC-opslagpad.
- **CBS:** bij eenduidige actieve CBS-code + referentieversie wordt uitsluitend een officieel, laagste categorie overgenomen. Ontbrekende of inactieve doelregistraties krijgen een verhoogde versie, `confirmation_source='synonym:<bronproduct-id>'` en de gebruikelijke `global_product_cbs_history`-rij. `confirmed_by` is de actor van de bevestigde synoniemrelatie. De officiële CBS-referentie en eerdere historische records blijven intact.
- **Conflicten:** meerdere bevestigde GPC-Bricks of CBS-code/referentieparen in dezelfde groep blokkeren uitsluitend de overname voor dát classificatiesysteem, **niet** de synoniemregistratie of het andere systeem. Geen overschrijving. API antwoordt aanvullend met `classification_inheritance.conflicts`; de bestaande centrale overlay-melding wijst de gebruiker op te controleren conflicten.
- Bij herhaling worden geen extra bestaande classificaties of historische records gemaakt. Oude clients behouden het bestaande `linked` / `already_linked`-antwoord; de optionele `classification_inheritance` verschijnt alleen als er een overname of conflict is.
- De implementatie kopieert geen barcode, GTIN, winkelcode, artikelnaam, huishoud- of voorraadrelatie.
- De bestaande GPC/CBS-handmatige toekenningsroutes blijven bestaan. Het centraliseren van alle schrijfpaden en het oplossen van conflicten via een aparte workflow zijn geplande vervolgtaken; deze PR introduceert geen duplicaatclassificatietabellen.

## Gerichte regressie

De synoniementest breidt de reeds geïsoleerde PostgreSQL-testdatabase uit met minimale canonieke GPC- en CBS-autoriteit voor deze proef en controleert:
1. A→B automatische overname van beide classificaties.
2. B→A automatische overname.
3. A–B–C ketenovername, zonder productidentiteiten samen te voegen.
4. CBS-conflict wordt zichtbaar en bestaande waarden blijven intact.
5. Idempotente herhaling, met één CBS-historie-item.
6. Verplichte rollback bij een fout: geen losse synoniemkoppeling of classificatie.

**Opmerking:** een bevestigde relatie en automatische overname zijn geen bewijs dat de bestaande `Bijna op`-groepering of ED2-status zelfstandig verandert; het toepasselijke afzonderlijke ketencontract blijft leidend. Geen runtimegebruikersdata of Docker-/productieactie tijdens deze PR.


## Samenhang met PR #646 — winkelonafhankelijke synoniemen

De actuele PO-beslissing is dat **de winkel nooit een matchcriterium of
bevestigingsvoorwaarde voor synoniemen is**. Deze classificatieovername wordt
daarom uitsluitend getriggerd door een expliciet, volgens de actuele
artikel-/GS1-identiteitsvoorwaarden bevestigd `article_synonym_links`-paar,
ongeacht of beide artikelen dezelfde, verschillende of onbekende winkelherkomst
hebben. Winkelgegevens mogen niet mee worden gekopieerd en spelen geen rol
bij GPC-/CBS-overname of conflictbesluiten.

PR #645 bevat nog de oudere implementatie van
`backend/app/services/article_synonym_service.py` en van het
Artikel-synoniemen-scherm. Die mogen **niet** over de modernere winkelonafhankelijke
implementatie van Draft-PR #646 worden teruggezet. De integratie moet daarom
pas op een kandidaat die PR #646 bevat worden uitgevoerd, met behoud van
de actuele `suggest_pairs`, `confirm_pairs`, de dubbele artikeltabel
en het bewaren van selectie, en aanvullend de bestaande transactionele
`propagate_confirmed_classifications`-aanroep en overlayrespons uit PR #645.

Voor Ready van PR #645 zijn gerichte ketentests vereist voor:
- bevestiging bij **onbekende winkel** met GPC- én CBS-overname;
- bevestiging bij **gelijke winkel** met dezelfde overname;
- bevestiging bij **verschillende winkels** met dezelfde overname;
- conflicterende bestaande officiële GPC/CBS-codes zonder overschrijven;
- idempotente retry en rollback binnen één transactie;
- correcte classificatieovername zonder automatische product-/voorraadmutaties.

Deze paragraaf is een integratiecontract, **geen claim** dat de branches
al technisch zijn samengevoegd of dat deze nieuwe regressies groen zijn.


## Geïntegreerde kandidaat op nieuwe main (4 november 2026)

PR #646 is op `main@5d7c02e0ff624437eb7d8b72b82970fd4723bb83` gemerged. PR #645 neemt daarvan de volledige winkelonafhankelijke synoniemenservice, twee tabellen, ontkoppelen en de bestaande verklarende blokkerings-overlay als basis. Alleen de transactionele GPC/CBS-erfservice, responsmelding en isolatie-/regressietests worden daarop toegevoegd. De oude UI en winkelgebonden matching uit de oorspronkelijke #645-branch worden niet teruggezet. De classificatieovername verandert geen barcodes, winkelherkomst, huishoudartikelen of voorraad. Eventuele conflicten per systeem behouden hun bestaande officiële waarden en melden zich via de centrale Inhuis-overlay. Alleen een latere expliciete PO-GO kan #645 mergen.

### Ontkoppeling tijdens classificatieovername

Ook de bestaande `/unlink`-transactie neemt nu dezelfde PostgreSQL-advisory lock als `/link`, vóór zij de actuele paren leest. Daarmee kan een gelijktijdige ontkoppeling niet een verouderde synoniemgroep laten classificeren. Ontkoppelen blijft uitsluitend de geselecteerde directe synoniemrelatie verwijderen; eerder bevestigde of via synoniemen overgenomen GPC-/CBS-gegevens worden hierdoor **niet** automatisch teruggedraaid. Voor een andere indeling is afzonderlijke expliciete en bevoegde correctie nodig.


## Nieuw PO-besluit: conflicterende bestaande classificaties expliciet laten kiezen (4 november 2026)

Wanneer beide artikelen verschillende officiële GS1 GPC-Bricks en/of
CBS ECOICOPv2-codes hebben, geldt de eerdere instructie "alleen waarschuwen,
nooit overschrijven" **niet meer voor een door de gebruiker expliciet
gekozen en bevoegd bevestigde voorkeur**. Geen van beide classificaties krijgt
automatisch voorrang. De keuze gebeurt vóór het vastleggen van de
synoniemrelatie en is **per systeem onafhankelijk** (GS1 GPC links/rechts en
CBS links/rechts), op basis van de actuele bestaande codes, bijbehorende
officiële Nederlandse omschrijvingen en CBS-referentieversies.

Het nieuwe read-only endpoint `POST /link/review` vergelijkt de actueel
vastgelegde centrale classificaties voor een gekozen artikelpaar. De normale
`POST /link` accepteert daarnaast expliciete keuzes met een serverberekende
snapshot. De server weigert ontbrekende, verouderde, vervalste of
onbevoegde keuzes, evenals identieke GTIN of gedeelde bevestigde
winkelartikelidentiteit. Verschillende GS1 GPC Bricks mogen uitsluitend
na expliciete bronkeuze worden gekoppeld en gecorrigeerd; hiervoor wordt
bovendien de bestaande `gpc.update`-bevoegdheid verlangd.
Voor CBS hergebruikt de bevestiging de bestaande officiële
`confirm_cbs_batch`-autoriteit met versiebewaking en historie.

De keuze schrijft alleen op centrale `global_product`-identiteiten, met
herkomst `synonym_review:<bronproduct>`, en past uitsluitend de andere
betrokken classificatie aan. Alle wijzigingen vinden in één bestaande
database-transactie plaats; **Annuleren** schrijft niets en
gelijktijdige wijzigingen leiden tot opnieuw beoordelen. Bij meer dan
één onderling afhankelijk conflicterend paar in een bulkselectie wordt
fail-closed gevraagd ze afzonderlijk te behandelen. De automatische overname
van **ontbrekende** classificaties en de bestaande bescherming van de
overige synoniemgroep blijven bestaan. Geen barcode-, aankoop-,
huishoud- of voorraadmutatie.
