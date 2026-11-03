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
