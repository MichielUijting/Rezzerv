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
