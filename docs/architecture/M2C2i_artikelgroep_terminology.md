# M2C2i Artikelgroep-terminologie

Status: ontwerp- en implementatienotitie bij `m2c2i-artikelgroep-uitpakken-terminology-github`.

## Besluit

De zichtbare term **Mijn artikel** wordt niet langer gebruikt als functioneel hoofdbegrip in Uitpakken. Het technische voorraadanker blijft bestaan, maar heeft voor de gebruiker geen zelfstandige betekenis.

## Nieuwe functionele lijn

- **Artikelnaam** is de naam die Rezzerv toekent of voorstelt op basis van bonregel, classificatie, productdata of externe databases.
- **Artikelgroep** is een optionele huishoudelijke ordeningslaag.
- **Voorraadartikel-ID** of `household_article_id` blijft een technische sleutel voor voorraad, historie en koppelingen.

## Scope eerste implementatiestap

Deze eerste stap verwijdert de zichtbare terminologie via de frontend buildlaag:

- `Mijn artikel` wordt in frontendbronnen weergegeven als `Artikelgroep`.
- `mijn artikel` wordt in frontendbronnen weergegeven als `artikelgroep`.
- Er is geen databasewijziging.
- Er is geen wijziging in receipt ingestion, OCR, parsering of voorraadmutatie.
- Er is geen wijziging in externe kandidaatselectie.

## Vervolgstap

Een latere release voegt echte Artikelgroepen toe als huishoudinstelling, inclusief beheer in Instellingen en optionele weergave in Uitpakken en Voorraad.

## Guardrail

Artikelgroep is gebruikersordening. Artikelgroep bepaalt geen productidentiteit, vervangt geen GTIN/EAN, vervangt geen externe classificatie en mag geen voorraadmutatie veroorzaken.
