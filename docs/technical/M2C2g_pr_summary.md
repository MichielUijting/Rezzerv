# M2C2g PR summary

Externe kandidaten selecteren en verwerken in de artikelcatalogus.

## Scope

- tab **Catalogus verwerken** in Externe databases
- per bonartikel maximaal één externe kandidaat kiezen
- gekozen kandidaat verwerken in de artikelcatalogus
- geen huishoudartikel-aanmaak
- geen voorraadmutatie
- geen Mijn-artikel-aanmaak

## UI-conformiteitscheck

Deze PR moet aantoonbaar voldoen aan de standaard Rezzerv UI-conventies:

- tabellen gebruiken `frontend/src/ui/Table.jsx` als basiscomponent;
- er worden geen losse HTML-tabellen buiten het standaard `Table`-component geïntroduceerd;
- tabelselectie gebruikt Rezzerv-groen en geen browserblauw;
- meldingen lopen via het standaard melding-overlaypatroon met titel **Melding** en knop **Sluiten**;
- geen losse custom inline-meldingen onder tabelknoppen;
- contextinformatie bij de tabel is functioneel zichtbaar, in dit geval **Bonartikel in behandeling**;
- eventuele afwijkingen van de standaard tabelconventies moeten vooraf expliciet worden benoemd.

## Ontwikkelafspraak voor vervolgwerk

Voor elk nieuw Rezzerv-onderdeel met tabellen geldt voortaan standaard:

1. eerst controleren welk standaard UI-component bestaat;
2. standaardcomponent hergebruiken;
3. afwijkingen alleen met expliciete reden;
4. PO-test uitbreiden met een UI-conformiteitscheck.
