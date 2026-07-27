# ADR – Nederlandse omschrijving voor GS1 GPC Brick-Producttypen

**Status:** vastgesteld  
**Versie:** 1.0  
**Datum:** 27 juli 2026  
**Besluitnemer:** Product Owner Rezzerv  
**Scope:** Productcatalogus, Producttypen en Bijna op

## Context

Rezzerv gebruikt het GS1 GPC Brick-niveau als Producttype. De officiële GPC-catalogus bevat een Engelstalige en een Nederlandstalige publicatie. Tot nu toe kon de applicatie afhankelijk van importvolgorde of bron een Engelse Brick-omschrijving als zichtbare Producttypenaam gebruiken.

Voor de huidige Nederlandse Rezzerv-app is dat niet wenselijk. De gebruikersinterface, instellingen, migratieanalyse en Bijna-op-uitkomsten moeten Nederlandse Producttypeomschrijvingen tonen. Tegelijk blijft de Engelse officiële term nodig als bronreferentie, voor matching, controle en toekomstige meertaligheid.

## Ontwerpbesluit

1. Iedere actieve GS1 GPC Brick wordt centraal vastgelegd met minimaal:
   - `gpc_brick_code`;
   - `gpc_brick_name_en`;
   - `gpc_brick_name_nl`.
2. Waar beschikbaar worden ook Class-, Family- en Segmentomschrijvingen afzonderlijk in Engels en Nederlands bewaard.
3. De Engelse term wordt niet vervangen door de Nederlandse vertaling; beide blijven naast elkaar beschikbaar.
4. Voor de huidige Rezzerv-app is `gpc_brick_name_nl` de verplichte zichtbare Producttypeomschrijving.
5. `product_inventory_groups.display_name` wordt voor officiële GPC-Producttypen gesynchroniseerd met `gpc_brick_name_nl`.
6. Een Nederlandse synchronisatie wordt geblokkeerd wanneer één of meer actieve Bricks geen Engelse of Nederlandse omschrijving hebben.
7. De synchronisatie wijzigt geen voorraad, huishoudartikelen, Producttypekoppelingen of Bijna-op-instellingen.
8. GET-routes blijven read-only. Import en synchronisatie worden uitsluitend via expliciete adminmutaties uitgevoerd.

## Technische vertaling

De centrale tabel `gpc_product_groups` bevat taalgescheiden velden voor Brick, Class, Family en Segment.

De gecombineerde importvolgorde is:

1. gebundelde officiële Engelse GPC-catalogus importeren;
2. officiële Nederlandse GPC-publicatie importeren;
3. taalversies afzonderlijk vastleggen;
4. volledigheid controleren;
5. Nederlandse namen activeren in `product_inventory_groups`.

De Producttype-identiteit blijft:

```text
gpc:<8-cijferige Brick-code>
```

De taal wijzigt dus alleen de omschrijving, nooit de technische sleutel.

## Gevolgen

- Alle huidige Producttypeselecties en Bijna-op-presentaties gebruiken Nederlandse omschrijvingen.
- Engelse termen blijven beschikbaar voor audit, matching en toekomstige meertalige ondersteuning.
- Importvolgorde kan de zichtbare Producttypenaam niet meer stilzwijgend terugzetten naar Engels.
- Een onvolledige vertaalset wordt zichtbaar als blokkade en niet als stille fallback geaccepteerd.

## Acceptatiecriteria

1. Alle actieve Bricks hebben zowel `gpc_brick_name_en` als `gpc_brick_name_nl`.
2. Voor iedere actieve officiële GPC-groep is `product_inventory_groups.display_name` gelijk aan `gpc_brick_name_nl`.
3. De Engelse naam blijft ongewijzigd beschikbaar.
4. De synchronisatie verandert het aantal voorraadregels en voorraadgebeurtenissen niet.
5. De backendcontracttest eindigt met `GPC_DUTCH_LOCALIZATION_CONTRACT_GREEN`.

## Niet gewijzigd

- Het besluit dat Brick het Producttypeniveau is.
- Producttypecodes en koppelsleutels.
- Huishoudspecifieke instellingen.
- Voorraadstanden en inventory events.
- Artikelgroepen.
- Producttypekoppelingen van globale producten.
