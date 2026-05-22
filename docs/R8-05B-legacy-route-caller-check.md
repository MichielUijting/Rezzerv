# R8-05B — Caller-check legacy artikelroutes

Status: uitgevoerd als caller-check  
Scope: frontend, scripts, regression tooling en documentatie  
Runtime-impact: geen  
Database-impact: geen  
Parser/OCR-impact: geen  

## Doel

Controleren of de oude `LEGACY` routes onder `/api/articles/*` nog actief door de applicatie of tooling worden aangeroepen voordat ze in R8-05C verwijderd worden.

## Gecontroleerde routefamilie

```text
/api/articles/*
```

Specifiek de 10 routes uit R8-05A:

```text
/api/articles/barcode-scan
/api/articles/household-details
/api/articles/product-details
/api/articles/{article_id}
/api/articles/{article_id}/archive
/api/articles/{article_id}/automation-override
/api/articles/{article_id}/enrich
```

## Zoektermen

De repo is gecontroleerd op onder meer:

```text
/api/articles
api/articles
articles/
barcode-scan
product-details
household-details
automation-override
household-articles
```

## Bevinding

Er zijn geen actieve frontend-, script- of tooling-callers gevonden die rechtstreeks de oude `/api/articles/*` routefamilie aanroepen.

De moderne productieroutes bestaan al onder:

```text
/api/household-articles/*
/api/products/*
/api/purchases/*
```

## Conclusie

R8-05B vereist geen caller-migratie in de huidige codebasis.

De oude `/api/articles/*` routes lijken nog uitsluitend als backend-compatibilitylaag in runtime aanwezig te zijn.

## Advies

Ga door met R8-05C:

- verwijder de oude `/api/articles/*` route-decorators uit de backend;
- laat moderne `/api/household-articles/*`, `/api/products/*` en `/api/purchases/*` routes intact;
- rebuild runtime;
- controleer `/api/admin/route-governance`;
- acceptatiecriterium: `LEGACY = 0`.

## Stopregels voor R8-05C

Stop en herstel als één van deze flows faalt:

1. login;
2. voorraad openen;
3. artikeldetail vanuit voorraad openen;
4. huishoudartikel bijwerken;
5. barcode-aankoop of productidentificatie;
6. kassabonregel koppelen aan artikel;
7. product enrichment.

## Acceptatiecriteria R8-05B

R8-05B is klaar wanneer:

- caller-check is vastgelegd;
- geen nog-te-migreren callers zijn gevonden;
- geen runtimewijziging is gedaan;
- vervolgopdracht R8-05C concreet is vastgesteld.
