# M2C2i Artikelgroep - Testafspraak

Omdat Uitpakken onder de frontend-regressiescope valt, mag deze branch niet naar main zonder actuele frontend-regressie.

## Minimale gate

- Docker build opnieuw uitgevoerd.
- Backend health ok.
- Frontend-regressie groen.
- Visuele controle: Uitpakken toont geen `Mijn artikel`.
- Geen database-, parser-, OCR- of voorraadwijzigingen in de diff.

## Merge

Niet mergen zonder expliciet akkoord van de PO na controle van PR-diff en regressie-uitkomst.
