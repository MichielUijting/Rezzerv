# Catalogusidentiteit per kassabonartikel — PO-besluit 12 november 2026

Status: functioneel PO-contract voor de Catalogus en de koppeling van bonartikelen.

## Begrippen

- **Kassabonomschrijving**: de tekst van het artikel op de kassabon, voor de identiteit stabiel genormaliseerd (spaties, hoofdletters en leestekens).
- **Bonartikelnummer**: de originele winkelartikelcode op die kassabon; voorloopnullen blijven behouden.
- **Artikel-/barcode**: de GTIN/EAN van één actief Catalogusproduct; geen bonartikelnummer.
- **Winkelketen**: canonieke retailer, waarbij bewezen aliassen zoals AH / Albert Heijn of Lidl / Lidl Nederland hetzelfde domein vormen.

## Uniciteit

**(Winkelketen, kassabonomschrijving, bonartikelnummer) → maximaal één Artikel-/barcode.**

Een kassabonomschrijving kan bij dezelfde winkelketen meerdere bonartikelnummers hebben. Die nummers kunnen bewust naar hetzelfde Catalogusproduct verwijzen. Het bonartikelnummer *alleen* mag dus niet bepalen dat twee verschillende kassabonomschrijvingen hetzelfde artikel zijn.

Wanneer de drie bronvelden aanwezig zijn, moet de herkenning de volledige combinatie gebruiken. Als een oude bron de omschrijving mist, is een code-only koppeling alleen bruikbaar als die eenduidig is. Bij meerdere mogelijke producten of conflicterende bewijsbronnen is de uitkomst *conflict*, niet een willekeurige match.

Voorbeeld:

| Winkel | Bontekst | Bonartikelnummer | Artikel-/barcode |
|---|---|---|---|
| Lidl | Melk halfvol | 0012345 | 8712345678906 |
| Lidl | Melk halfvol | 0087654 | 8712345678906 |
| Lidl | Yoghurt naturel | 0012345 | andere unieke GTIN |

De eerste twee regels zijn toegestaan. De laatste regel is alleen toegestaan als de volledige bonomschrijving+code naar één ander product verwijst; code-only herkenning moet bij twijfel stoppen.

## Beheer en gegevensbehoud

- Een platformbevoegde beheerder kan in Catalogusdetail de huidige combinaties bekijken, de juiste koppeling expliciet bevestigen, een bronbewezen bonartikelnummer toevoegen en een exact afgebakende foutieve koppeling corrigeren.
- Een nieuwe combinatie mag alleen worden toegevoegd als die aantoonbaar op een bestaande, niet-verwijderde fysieke productbonregel voorkomt en de doelbarcode uniek hoort bij een actief Catalogusproduct.
- Een correctie mag geen bestaande household-article-, voorraad-, bon-, event- of classificatiegegevens wijzigen. Als reeds bestaande huishoudartikelen aan de oude productidentiteit hangen, moet de correctie afzonderlijk beoordeeld worden.
- Geen automatische samenvoeging van huishoudartikelen; `household_articles.id` blijft de huishoudspecifieke identiteit.
- Een bevestiging of correctie wordt toegeschreven aan de werkelijke ingelogde bevoegde gebruiker.
- Bij historische incomplete of conflicterende identiteiten: toon een controleerbare fout, schrijf niets en laat de bron ongewijzigd.

## Verplichte regressies

1. Gelijke bontekst, verschillende bonartikelnummers mogen beide worden bevestigd.
2. Gelijke bonartikelcode, verschillende bontekst kunnen bij een verschillend Catalogusproduct horen.
3. Gelijke volledige broncombinatie naar twee verschillende Catalogusproducten is een conflict.
4. Een bron zonder bevestigde omschrijving mag niet stilzwijgend door een tekstmatch worden gekoppeld.
5. Een onjuiste of ontbrekende kassabonbron blokkeert het handmatig toevoegen.
6. Correctie met bestaande huishoudartikelverwijzingen of concurrente wijzigingen stopt zonder voorraad-/bonmutatie.
7. Bevestigen vereist platformpermissie en legt de werkelijke beoordelende gebruiker vast.
