# Huishoudartikel-identiteit — Slice 2 impactanalyse

Status: bindende implementatieblauwdruk
Branchbasis: `feature/uitpakken-dagartikelen-release-b`
Analysebasis: branch-head na frontendadapter-opruiming (`23adb4fc`)

## 1. Doel

Binnen Uitpakken, Artikelgroepen en Voorraad is `household_articles.id` de enige functionele identiteit van een Huishoudartikel. Namen, voorraadregels, mockopties en `live::<naam>`-waarden mogen niet als blijvende artikelidentiteit functioneren.

## 2. Bevestigde huidige situatie

### Frontend

- `StoreBatchDetailPage.jsx` gebruikt `matched_household_article_id` en bewaart de gekozen waarde als `articleId`.
- De algemene HTTP-laag herschrijft artikelopties niet meer.
- `householdArticleOptionAdapter.js` en de adaptertest zijn verwijderd.
- Uitpakken consumeert `/api/store-review-articles` nu rechtstreeks.

### Backend — canonieke bron aanwezig

De tabel `household_articles` bevat de echte identiteit. Bestaande routes voor artikeldetail gebruiken al een combinatie van actief huishouden en `household_article_id`.

### Backend — concurrerende paden nog aanwezig

`get_store_review_article_options` combineert momenteel:

1. `MOCK_ARTICLE_OPTIONS`;
2. records uit `household_articles`;
3. losse namen uit `inventory`;
4. gegenereerde `live::<artikelnaam>`-ID's.

Verder accepteren of produceren de volgende functies nog niet-canonieke identiteiten:

- `build_live_article_option_id`;
- `resolve_review_article_option`;
- `resolve_processing_article`;
- `find_generic_existing_article_match`;
- delen van fixtures en seeddata die `build_live_article_option_id(...)` opslaan;
- naamgebaseerde terugval via `inventory.naam` en `household_articles.naam`.

## 3. Risicoanalyse

### Hoog risico

- Historische `purchase_import_lines.matched_household_article_id`-waarden met prefix `live::`.
- Historische `suggested_household_article_id`-waarden met prefix `live::`.
- `store_import_memory.matched_household_article_id` met een niet-canonieke waarde.
- Voorraadhistorie of events die alleen `article_id`/artikelnaam bevatten.
- Gelijke artikelnamen binnen één huishouden: automatische naammigratie kan ambigu zijn.

### Middel risico

- Tests en fixtures die mock-ID's `1` t/m `5` verwachten.
- Importlogica die een voorraadnaam als bestaande artikeloptie presenteert.
- Generieke naamreductie, bijvoorbeeld `Volkoren pasta` naar `Pasta`.

### Laag risico

- Frontendweergavelabels; die mogen nog naamvelden combineren zolang de sleutel canoniek blijft.
- Merk- en locatie-defaults; deze kunnen rechtstreeks aan `household_article_id` gekoppeld blijven.

## 4. Bindende migratieregels

Een oude artikelreferentie mag alleen automatisch worden omgezet wanneer exact één record in `household_articles` binnen hetzelfde huishouden kan worden vastgesteld.

Resolutievolgorde:

1. waarde is al een bestaand `household_articles.id` binnen hetzelfde huishouden → behouden;
2. waarde is `live::<naam>` en exact één genormaliseerde naamovereenkomst bestaat binnen hetzelfde huishouden → vervangen door die ID;
3. een historische regel heeft naast de oude waarde al een ondubbelzinnige gekoppelde `household_article_id` in gerelateerde data → die ID gebruiken;
4. nul of meerdere kandidaten → niet gokken, migratie registreren als onopgelost en verwerking blokkeren met een duidelijke fout.

Nooit toegestaan:

- zoeken buiten het actieve huishouden;
- de eerste naamtreffer kiezen;
- stil een nieuw Huishoudartikel maken tijdens migratie;
- `inventory.naam` als primaire sleutel gebruiken;
- een mock-ID als productie-identiteit behouden.

## 5. Implementatievolgorde

### Slice 2B1 — inventarisatie en migratievoorziening

- Voeg een gerichte datacontrole toe voor `live::` en niet-bestaande Huishoudartikel-ID's in:
  - `purchase_import_lines.matched_household_article_id`;
  - `purchase_import_lines.suggested_household_article_id`;
  - `store_import_memory.matched_household_article_id`;
  - `inventory.household_article_id`;
  - `inventory_events.household_article_id` waar relevant.
- Maak de migratie idempotent.
- Rapporteer aantallen: al canoniek, gemigreerd, onopgelost, ambigu.

### Slice 2B2 — canonieke artikeloptieroute

`/api/store-review-articles`:

- vereist een geldige huishoudcontext;
- selecteert uitsluitend actieve `household_articles` van het actieve huishouden;
- retourneert minimaal:
  - `id`;
  - `household_article_id` met dezelfde waarde;
  - `name`;
  - `article_group_id`;
  - optionele merk- en locatie-defaults;
- retourneert nooit `live::`-ID's, mock-ID's of losse voorraadnamen.

### Slice 2B3 — resolvers normaliseren

- `resolve_review_article_option` accepteert alleen een bestaande Huishoudartikel-ID binnen hetzelfde huishouden.
- `resolve_processing_article` retourneert alleen een canonieke ID.
- `find_generic_existing_article_match` mag hoogstens als suggestiemechanisme blijven bestaan en mag geen identiteit meer vervangen.
- `build_live_article_option_id` verwijderen zodra productiecode, fixtures en migratie er niet meer van afhankelijk zijn.

### Slice 2B4 — voorraad en historie

Voorraadmutaties gebruiken uitsluitend:

`household_id + household_article_id + space_id/sublocation_id`

`inventory.naam` blijft een presentatiewaarde of snapshot en is geen matchcriterium.

### Slice 2C — fixtures en tests

- Vervang mock- en `live::`-ID's door expliciet aangemaakte Huishoudartikelen.
- Voeg een contracttest toe: `/api/store-review-articles` levert uitsluitend bestaande UUID/ID-waarden uit `household_articles` van het actieve huishouden.
- Voeg een contracttest toe: geen resultaat-ID begint met `live::`.
- Voeg een migratietest toe voor één ondubbelzinnige `live::`-waarde.
- Voeg een migratietest toe die een ambigue naam bewust niet migreert.

## 6. Vereiste regressieketen

1. backendgerichte tests voor migratie en route;
2. kassabon-voorraadketen 12/12;
3. centrale frontendregressie 29/29 of hoger;
4. huishouden-0-contractscan;
5. PO-test:
   - Mijn artikel in Uitpakken selecteren;
   - hetzelfde Huishoudartikel in Artikelgroepen terugvinden;
   - normale verwerking verhoogt de juiste voorraadpositie;
   - Direct/direct registreert financieel maar wijzigt voorraad niet;
   - F5 behoudt dezelfde koppeling;
   - wijziging van Artikelgroep is na herladen overal zichtbaar.

## 7. Stopvoorwaarden

De implementatie stopt zonder commit wanneer:

- een migratie meerdere Huishoudartikelen voor dezelfde oude waarde vindt;
- een productiepad nog een `live::`-ID schrijft;
- `/api/store-review-articles` records buiten het actieve huishouden kan tonen;
- een voorraadmutatie nog uitsluitend op artikelnaam matcht;
- een bestaande regressie rood wordt.

## 8. Definitie van gereed

Slice 2 is pas afgerond wanneer:

- alle actieve artikelkeuzes een echte `household_article_id` gebruiken;
- de route geen mocks, voorraadnamen of `live::`-waarden meer levert;
- historische waarden gecontroleerd zijn gemigreerd of expliciet als onopgelost zijn gemarkeerd;
- Uitpakken, Artikelgroepen en Voorraad dezelfde ID gebruiken;
- alle verplichte regressies groen zijn.
