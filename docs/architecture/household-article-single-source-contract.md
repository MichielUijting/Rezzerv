# Huishoudartikel als enige functionele artikelbron

Status: bindend contract voor Uitpakken, Artikelgroepen en Voorraad.

## Kernregel

`household_articles.id` (`household_article_id`) is de enige functionele identiteit voor een artikel binnen een huishouden.

De zichtbare begrippen **Mijn artikel** in Uitpakken en **Voorraadartikel** in Voorraad zijn geen afzonderlijke domeinentiteiten. Het zijn twee schermcontexten van hetzelfde huishoudartikel.

## Relaties

- Een kassabonregel blijft een `receipt_table_line` of `purchase_import_line`.
- De keuze **Mijn artikel** schrijft uitsluitend de verwijzing `matched_household_article_id` naar `household_articles.id`.
- De artikelgroep is een eigenschap/relatie van datzelfde huishoudartikel via `household_articles.article_group_id`.
- Standaardverwerking is een eigenschap van datzelfde huishoudartikel via `household_articles.default_inventory_handling`.
- Een voorraadpositie is een projectie in `inventory` met `inventory.household_article_id` naar hetzelfde huishoudartikel, aangevuld met locatie en hoeveelheid.
- Een aankoop- of voorraadgebeurtenis verwijst naar hetzelfde `household_article_id`.

## Verboden dubbele bronnen

De volgende waarden mogen niet als zelfstandige functionele artikelidentiteit worden gebruikt:

- zichtbare artikelnaam;
- bontekst;
- `inventory.id`;
- een frontendoptie-ID of `live::`-alias;
- een gekopieerde artikelgroep op een importregel als permanente bron;
- een afzonderlijk "Mijn artikel"-record;
- een afzonderlijk "Voorraadartikel"-record.

Namen zijn presentatie. Alleen `household_article_id` bepaalt welk huishoudartikel bedoeld is.

## Gedrag per scherm

### Uitpakken

- Toont een gebruikersvriendelijke kolomnaam, maar kiest een `household_article_id`.
- Leest artikelgroep en standaardverwerking van `household_articles`.
- Mag een tijdelijke verwerking of locatie per importregel opslaan, maar maakt geen kopie van het huishoudartikel.

### Artikelgroepen

- Wijzigt `article_group_id` en standaardverwerking op `household_articles`.
- De wijziging is onmiddellijk zichtbaar in Uitpakken en Voorraad omdat alle schermen hetzelfde record lezen.

### Voorraad

- Toont voorraadposities gegroepeerd of uitgesplitst naar locatie.
- Iedere zichtbare actieve voorraadregel moet een geldige `household_article_id` hebben.
- Artikelnaam en artikelgroep worden via `household_articles` gelezen; zij worden niet als concurrerende waarheid uit `inventory.naam` afgeleid.

## Verwerkingscontract

1. Een importregel wordt gekoppeld aan exact één `household_article_id`.
2. De effectieve verwerking wordt bepaald uit een tijdelijke regelafwijking en anders uit `household_articles.default_inventory_handling`.
3. De financiële aankoopregistratie gebruikt altijd datzelfde `household_article_id`.
4. Bij normale opslag wordt `inventory` bijgewerkt met datzelfde `household_article_id`.
5. Bij directe consumptie wordt geen voorraadpositie gemaakt; aankoop en consumptie blijven wel aan hetzelfde huishoudartikel gekoppeld.

## Migratie- en opruimregel

Bestaande actieve voorraadregels zonder geldig `household_article_id`, met een verkeerd huishouden of met een tijdelijke alias moeten via een expliciete migratie worden hersteld of geblokkeerd. Nieuwe naamgebaseerde fallback- of synchronisatiecode is niet toegestaan.

## Verplichte regressies

- Uitpakken kiest Appel en slaat het echte `household_article_id` van Appel op.
- Wijziging van artikelgroep bij Appel is zonder synchronisatiestap zichtbaar in Uitpakken en Voorraad.
- Normale aankoop verhoogt voorraad van hetzelfde huishoudartikel.
- Directe aankoop registreert het bedrag maar maakt geen voorraadpositie.
- Twee huishoudartikelen met dezelfde naam in verschillende huishoudens blijven volledig geïsoleerd.
- Herladen en F5 veranderen de gekozen artikelidentiteit niet.
