# R8-05A — Beoordeling LEGACY-routes

Status: uitgevoerd als governance-beoordeling
Scope: resterende `LEGACY` routes onder `/api/articles/*`
Runtime-impact: geen
Database-impact: geen
Parser/OCR-impact: geen

## Aanleiding

Na R8-04D bevat het route-governance manifest geen `DEV_ONLY` routes meer. De resterende niet-productieklasse die inhoudelijke beoordeling vraagt is `LEGACY`.

Het actuele manifest toont 10 `LEGACY` routes. Deze vallen allemaal onder `/api/articles/*`.

## Doel

Bepalen of de oude artikelroutes nog nodig zijn of vervangen moeten worden door de moderne household-article routes:

```text
/api/household-articles/*
```

## Inventarisatie LEGACY-routes

| Route | Methode | Huidige functie | Modern alternatief | Advies |
|---|---|---|---|---|
| `/api/articles/barcode-scan` | POST | Artikel/barcode scan via oude artikelcontext | `/api/products/identify` of `/api/purchases/barcode` | MIGREREN |
| `/api/articles/household-details` | GET | Oude household-artikeldetails ophalen | `/api/household-articles/{household_article_id}` + detail-subroutes | MIGREREN |
| `/api/articles/household-details` | PATCH | Oude household-artikeldetails bijwerken | `/api/household-articles/{household_article_id}` PATCH of `/settings` | MIGREREN |
| `/api/articles/product-details` | GET | Oude productdetails ophalen | `/api/household-articles/{household_article_id}/product` | MIGREREN |
| `/api/articles/{article_id}` | GET | Oude artikeldetailroute | `/api/household-articles/{household_article_id}` | MIGREREN |
| `/api/articles/{article_id}` | DELETE | Oude artikeldeleteroute | `/api/household-articles/{household_article_id}` DELETE | MIGREREN |
| `/api/articles/{article_id}/archive` | POST | Oude artikelarchive-route | `/api/household-articles/{household_article_id}/archive` | MIGREREN |
| `/api/articles/{article_id}/automation-override` | GET | Oude automation override ophalen | `/api/household-articles/{household_article_id}/automation-override` GET | MIGREREN |
| `/api/articles/{article_id}/automation-override` | PUT | Oude automation override wijzigen | `/api/household-articles/{household_article_id}/automation-override` PUT | MIGREREN |
| `/api/articles/{article_id}/enrich` | POST | Oude artikelenrichment | `/api/household-articles/{household_article_id}/enrich` of `/api/products/enrich` | MIGREREN |

## Beoordeling per criterium

| Criterium | Bevinding |
|---|---|
| Productierisico | Middelmatig: routes wijzigen/verwijderen artikel- en household-artikeldata |
| Functionele waarde | Waarschijnlijk historisch/compatibiliteit |
| Moderne alternatieven aanwezig | Ja, voor alle hoofdflows |
| Direct verwijderen verantwoord | Nee, eerst referentiecheck in frontend/scripts nodig |
| Aanbevolen richting | Omzetten naar moderne routes en daarna oude aliases verwijderen |

## Belangrijkste conclusie

Geen van de 10 routes hoeft als blijvende `LEGACY` route te worden behouden.

Alle routes krijgen voorlopig advies:

```text
MIGREREN
```

Dus niet direct verwijderen, maar eerst alle callers omzetten naar moderne routes. Daarna kan de oude `/api/articles/*` laag als compatibilitylaag verwijderd worden.

## Aanbevolen vervolgstappen

### R8-05B — Referentiecheck en caller-migratie

Zoek expliciet naar gebruik van oude artikelroutes in:

- frontend;
- scripts;
- regression tooling;
- batchbestanden;
- documentatie;
- backend interne helpers.

Zet callers om naar:

```text
/api/household-articles/*
/api/products/*
/api/purchases/*
```

### R8-05C — Oude LEGACY-routes verwijderen

Pas nadat R8-05B is gevalideerd:

- verwijder `/api/articles/*` route-decorators;
- rebuild runtime;
- controleer route-governance;
- acceptatiecriterium: `LEGACY = 0`.

## Stopregels

Stop en onderzoek eerst als:

1. artikelbeheer niet meer werkt;
2. voorraadregels niet meer openen;
3. artikeldetailpagina faalt;
4. barcodeflow faalt;
5. enrichment faalt;
6. kassabonregels niet meer aan artikelen gekoppeld kunnen worden.

## Acceptatiecriteria R8-05A

R8-05A is klaar wanneer:

- alle 10 legacy-routes zijn benoemd;
- per route een modern alternatief is vastgesteld;
- geen runtimewijziging is gedaan;
- vervolgopdracht R8-05B concreet is gedefinieerd.
