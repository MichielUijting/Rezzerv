# Herstelrelease — Uitpakken readiness en artikelmodel

Status: technisch contract voor implementatie

## Hoofddoel

Herstel de Uitpakken-flow zodat een kassabonregel naar Voorraad kan worden verwerkt zonder Artikelgroep, Universeel artikel of Producttype, zolang het technische huishoudartikelanker, de hoeveelheid en een geldige doellocatie beschikbaar zijn.

## Productbesluiten

1. De zichtbare term `Mijn artikel` vervalt uit de Uitpakken-UI en wordt vervangen door `Artikelgroep`.
2. Artikelgroep is huishoudspecifiek en optioneel. `Niet ingedeeld` is geldig.
3. Universeel artikel is niet vereist voor Uitpakken of Voorraad.
4. Producttype is niet vereist zolang geen Universeel artikel is gekoppeld.
5. Er mag geen definitief Universeel artikel bestaan zonder Producttype.
6. `household_article_id` blijft het interne technische anker voor voorraad, locaties, instellingen en historie.

## Ready-contract

Een geselecteerde Uitpakken-regel is verwerkingsklaar wanneer:

- een geldig `household_article_id` aanwezig of backendmatig resolveerbaar/aangemaakt is;
- `quantity > 0`;
- een geldige `target_location_id` aanwezig is;
- de regel nog niet verwerkt is.

De volgende velden mogen readiness nooit blokkeren:

- `article_group_id` / `selected_article_group_id`;
- `global_product_id` / `matched_global_product_id`;
- Producttype.

## Catalogus-invariant

Een huishoudartikel mag bestaan zonder Universeel artikel. Zodra een definitieve koppeling naar een Universeel artikel wordt vastgelegd, moet dat Universele artikel een Producttype hebben. De combinatie `Universeel artikel aanwezig + Producttype ontbreekt` is ongeldig als definitieve catalogustoestand.

## UI-contract Uitpakken

- De zichtbare kolom `Mijn artikel` wordt vervangen door `Artikelgroep`.
- Artikelgroep toont een optionele huishoudkeuze en ondersteunt `Niet ingedeeld`.
- Het interne `household_article_id` blijft buiten beeld maar wordt niet verwijderd.
- Een ontbrekende Artikelgroep mag geen waarschuwing of verwerkingsblokkade veroorzaken.
- De melding bij incomplete regels noemt uitsluitend werkelijk blokkerende voorwaarden, bijvoorbeeld artikelanker, aantal of locatie.

## Niet wijzigen

- Inventory-eventmodel.
- Bestaande voorraadmutaties.
- Receipt lifecycle Release B delete/reimport-logica.
- Household-isolatie en autorisatieregels.
- Productcatalogusrecords buiten de expliciete catalogus-invariant.

## Acceptatiecriteria

1. Bestaand huishoudartikel + aantal + locatie + geen Artikelgroep => verwerkbaar.
2. Geen Universeel artikel => verwerkbaar.
3. Geen Producttype en geen Universeel artikel => verwerkbaar.
4. Geen Artikelgroep, geen Universeel artikel en geen Producttype => verwerkbaar.
5. Geen locatie => geblokkeerd.
6. Aantal nul/ongeldig => geblokkeerd.
7. Geen geldig technisch huishoudartikelanker en niet backendmatig resolveerbaar => geblokkeerd.
8. Artikelgroep `Niet ingedeeld` => geldig en persistent.
9. Wijzigen Artikelgroep veroorzaakt geen inventory-event.
10. Definitieve koppeling naar Universeel artikel zonder Producttype => geblokkeerd.
11. De foutmelding noemt Artikelgroep niet meer als verwerkingsvoorwaarde.
12. De bestaande Kassa → Uitpakken → Voorraad-keten blijft regressievrij.

## Vastgestelde huidige fout

In `frontend/src/features/stores/StoreBatchDetailPage.jsx` bepaalt `deriveLineSelectionState` momenteel `isProcessable` met onder meer `hasArticleGroup`. Daardoor wordt een regel met geldig artikel/product en locatie ten onrechte geblokkeerd wanneer Artikelgroep leeg is. De bevestigingsmelding noemt Artikelgroep eveneens ten onrechte als verplichte voorwaarde.

Dit contract is leidend voor de herstelrelease.
