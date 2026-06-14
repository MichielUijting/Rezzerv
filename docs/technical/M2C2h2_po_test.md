# PO-test M2C2h-2 - Detailframe bonartikel met externe kandidaten

## Doel

Controleren dat het detailframe onder de hoofdtabel Bonartikelen functioneel is voor externe kandidaten en catalogusverwerking.

## Voorbereiding

cd C:\Users\Gebruiker\Rezzerv_Github
git switch m2c2h-detailframe-kandidaten
npm --prefix frontend run build

Open daarna:

http://localhost:5174/externe-databases

## Testpunten

1. Open Externe databases.
2. Controleer dat de tab Overzicht opent.
3. Controleer dat de hoofdtabel Bonartikelen voor externe herkenning zichtbaar is.
4. Dubbelklik op een bonartikel met externe kandidaten.
5. Controleer dat het detailframe onder de hoofdtabel opent.
6. Controleer dat het detailframe de bonartikelcontext toont.
7. Controleer dat de kandidatentabel zichtbaar is.
8. Controleer dat de kandidatentabel de kolommen Keuze, Kandidaat, Merk, Artikelnummer, GTIN/EAN, Omvang/gewicht, Bron, Score en Status toont.
9. Selecteer één kandidaat met de radio-knop.
10. Controleer dat slechts één kandidaat tegelijk geselecteerd kan zijn.
11. Controleer dat de knop Verwerk gekozen kandidaat in catalogus actief wordt.
12. Klik op Verwerk gekozen kandidaat in catalogus.
13. Controleer dat er een melding verschijnt over de catalogusverwerking.
14. Controleer dat de hoofdtabel daarna opnieuw geladen wordt.
15. Controleer dat er geen Mijn artikel is aangemaakt.
16. Controleer dat er geen voorraadmutatie is aangemaakt.
17. Controleer dat er geen huishoudartikel is aangemaakt.

## Verwachte uitkomst

M2C2h-2 is akkoord als de gebruiker vanuit één bonartikel de externe kandidaten kan bekijken, één kandidaat kan selecteren en de catalogusverwerking kan starten zonder huishoudartikel- of voorraadmutatie.

## Buiten scope

- Geen nieuwe matchinglogica.
- Geen Mijn artikel.
- Geen voorraadmutatie.
- Geen huishoudartikel.
- Geen DataTable-refactor.
