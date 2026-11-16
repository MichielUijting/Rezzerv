# Bijna op: Voorspeltermijn, bewezen equivalentie en foto

**PO-opdracht:** 16 november 2026.
**TEST_LEVEL_PROVISIONAL: L** — wijziging van Bijna-op-projectie in de backend en gekoppelde frontend/CI-authorities.

## Voorspeltermijn — één huishoudinstelling

- De bestaande instelling `almost_out_prediction_days` blijft de enige waarheid.
- Op **Instellingen → Bijna op** heet het veld **Voorspeltermijn (dagen)** in plaats van **Extra voorspeltermijn (dagen)**.
- Desktop én mobiel tonen in **Bijna op** boven de lijst **Voorspeltermijn: N dagen**.
- Alleen de huishoudbeheerder krijgt **Wijzigen**, **Opslaan** en **Annuleren**. De backend `PUT /api/household/almost-out-settings` blijft de autoriteit en weigert onbevoegde wijzigingen.
- De wijzigingsroute leest de meest recente instellingen vóór opslaan, behoudt boodschappenplanning, voorspelling ingeschakeld en beleidsmodus; bij een gelijktijdig gewijzigde voorspeltermijn moet de gebruiker opnieuw beoordelen. Na opslag wordt de Bijna-op-projectie opnieuw geladen.
- Wanneer de voorspelling is uitgeschakeld blijft het opgeslagen aantal zichtbaar, maar meldt de UI **voorspelling uitgeschakeld**; wijzigen schakelt voorspelling niet impliciet in.
- Bestaande businessregel blijft: effectieve horizon is `max(shopping_days, prediction_enabled ? prediction_days : 0)`; minimumvoorraad en inconsistentiecontrole blijven geldend.

## Matchen en synoniemen in Bijna op

- Een artikel verschijnt **alleen** wanneer de bestaande voorraad-/voorspelregels daar een geldige aanleiding voor geven. Matching is geen automatische reden om alle verwante artikelen permanent als Bijna op te markeren.
- Huishoudartikelen met **hetzelfde bewezen `global_product_id`** vormen één read-only geaggregeerd signaal. Alle `member_article_ids` blijven beschikbaar; hun voorraad en eventhistorie worden niet gemuteerd.
- Het bestaande `automatic_product_type`-contract en de expliciet bevestigde, verpakkingscompatibele synoniemen blijven leidend. Synoniemen zonder voldoende eenheids-/inhoudsbewijs, onvolledige veilige groep en onbewezen relaties worden nooit samengevoegd.
- Geen naamgebaseerde samenvoeging, GTIN-vervanging, wijziging van huishoudreferenties of cross-household aggregatie.
- De al bestaande `almost_out_hidden`-regels blijven op alle betrokken leden toegepast.

## Foto bij getoond signaal

1. Foto van het eigen Catalogusproduct.
2. Foto van een ander **aantoonbaar gegroepeerd** huishoudartikel (zelfde centrale product, veilig automatisch producttype of bevestigde compatibele synoniemgroep).
3. Bestaande alleen-lezen Catalogus-/identiteitsroute: bevestigde exacte match of **rechtstreeks** bevestigde Catalogussynoniemrelatie.
4. Pas **Geen foto** wanneer geen betrouwbaar beeld bestaat. Geen afbeelding van een willekeurig GPC-product, gelijkende naam of onbevestigde synoniemkandidaat.

De centrale resolvers gebruiken uitsluitend household-scoped artikelrijen en bestaande Catalogusidentiteit; nieuwe foto-opzoeklogica schrijft niet in de database.

## Testcontract

- Desktop én mobiel: waarde tonen, beheerder kan aanpassen, niet-beheerder alleen lezen, synchronisatie met Instellingen, behoud overige instellingsvelden, opnieuw laden van Bijna op.
- Exact hetzelfde bewezen centrale product in meerdere historische huishoudartikelen: één signaal, behoud groepsleden, geen dubbele telling; onzekere relaties afzonderlijk.
- Bevestigde verpakkingscompatibele synoniemen blijven correct gegroepeerd; onverenigbare eenheden niet.
- Fototest: eigen foto heeft voorrang, anders bevestigd groepslid, anders bestaande directe synoniemresolver; bij onvoldoende bewijs geen foto; geen writes of cross-household lek.
- Bestaande PostgreSQL-/API-/frontend-/ketenregressies en F7-gates blijven verplicht. Tests gebruiken uitsluitend geïsoleerde testdata.
