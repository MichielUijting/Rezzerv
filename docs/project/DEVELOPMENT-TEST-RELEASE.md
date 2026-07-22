# Ontwikkel-, test- en releaseproces

## Hoofdregel

Eén release of PR heeft één doel. UI-, backend-, infrastructuur-, styleguide- en patchwijzigingen worden niet onnodig gecombineerd.

## Werkstroom

1. scope en acceptatiecriteria vastleggen;
2. actuele documentatie en runtime controleren;
3. branch maken vanaf actuele `main`;
4. wijziging bouwen;
5. gerichte contracten en regressietests uitvoeren;
6. QA/QC-scopecontrole;
7. expliciete PO-GO;
8. merge met verwachte head-SHA;
9. mergecommit afzonderlijk tegen `main` verifiëren.

## Verplichte technische controles

Afhankelijk van wijzigingszwaarte: compile- en syntaxcontrole, backend/API-contracten, frontendbuild, Dockerbuild en start, healthcheck, databaseschema en migratiecontrole, Playwright-regressies, huishoud-/object-/rolcontracten, routecatalogus, kassabonketen-validatie en mergegate.

## Releasegate

Een release is technisch gereed wanneer relevante workflows groen zijn, scope en bestanden kloppen, geen onverklaarde route- of schemaafwijking bestaat, documentatie is bijgewerkt, QA/QC akkoord is en de PO expliciet GO geeft.

## Huidige M2C2n-baseline

Op 22 juli 2026: 194 routeregistraties, 194 unieke methode-padcombinaties, 0 dubbelen, 85 reads en 109 mutaties. Alle 16 afsluitworkflows waren groen op de definitieve WP-7-head.
