# Later opruimen: resterende Externe databases (1)-code

> **Uitsluitend registratie van vervolgwerk. Geen code- of datawijziging in deze PR.**
>
> GitHub-issue: [#660](https://github.com/MichielUijting/Rezzerv/issues/660).

## Achtergrond

De oude, zichtbare gebruikersfunctie **Externe databases (1)** is eerder verwijderd. De huidige gebruikersfunctie **Artikelbeheer** (voorheen Externe databases 2) gebruikt nog gedeelde diensten voor OFF, GS1, Catalogus, barcodekoppelingen en artikelherkenning. Naamgeving zoals `external_*` of het API-prefix `/api/external-databases` bewijst niet dat code ongebruikt is.

## Later te onderzoeken

- Oude kandidaatpromotie- en diagnoseroutes in `backend/app/api/system_routes.py`, waaronder `catalog/promote-candidate`, `catalog/promote-highest`, `retailers/{retailer_code}/diagnose-real-candidates`, `receipt-items/ensure-candidates`, `coverage/receipt-items`, `candidates` en `catalog/products`.
- Afzonderlijke administratieve `/api/admin/external-relations/batch*`-routes.
- Exclusieve legacy-services na objectieve caller-analyse; geen hele `external_*`-bestandsfamilie op naam schrappen.
- Het gebruikerszichtbare label **Externe databases 2** in de platforminstellingen; de Startpagina toont al **Artikelbeheer**.

## Veiligheidsgrenzen voor een toekomstige opdracht

1. Onderzoek de werkelijke callers vanuit UI, API, imports, achtergrondprocessen, CLI, tests en diagnostiek voordat een onderdeel verwijderd wordt.
2. Behoud alle actieve Artikelbeheer-, Catalogus-, OFF-, GS1-, synoniemen-, Kassa-, Uitpakken- en Voorraadfuncties.
3. Verwijder geen historische migraties, opgeslagen artikel-/bongegevens of databases en volumes.
4. Maak bij een latere expliciete PO-opdracht een **afzonderlijke implementatie-PR**, met gerichte regressies, verplichte gates en exact-kandidaatbewijs waar van toepassing.
5. Gebruik `docs/project/LEGACY-EXTERNAL-DATABASES-RETIREMENT.md` als eerder saneringsverslag, niet als actuele callerwaarheid.

## Scope van deze PR

Dit document registreert uitsluitend de toekomstige werkzaamheden die ook in issue #660 staan. **Geen applicatiecode, tests, configuratie, database, migratie, versie, runtime of productiedata wordt gewijzigd.**
