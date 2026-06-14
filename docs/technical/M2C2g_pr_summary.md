# M2C2g PR summary

Externe kandidaten selecteren en verwerken in de artikelcatalogus.

## Scope

- tab Catalogus verwerken in Externe databases
- per bonartikel maximaal een externe kandidaat kiezen
- gekozen kandidaat verwerken in de artikelcatalogus
- geen huishoudartikel-aanmaak
- geen voorraadmutatie
- geen Mijn-artikel-aanmaak

## UI-conformiteitscheck

Deze PR moet aantoonbaar voldoen aan de standaard Rezzerv UI-conventies:

- tabellen gebruiken frontend/src/ui/Table.jsx als basiscomponent;
- geen losse HTML-tabellen buiten het standaard Table-component;
- tabelselectie gebruikt Rezzerv-groen;
- meldingen lopen via het standaard melding-overlaypatroon;
- geen losse custom inline-meldingen onder tabelknoppen;
- contextinformatie bij de tabel is zichtbaar;
- tabelrijhoogte is 28 px;
- filterrij onder de kolomkoppen is aanwezig;
- sortering op relevante kolommen is aanwezig;
- paginering is aanwezig.

## Ontwikkelafspraak voor vervolgwerk

Voor elk nieuw Rezzerv-onderdeel met tabellen geldt voortaan standaard:

1. eerst controleren welk standaard UI-component bestaat;
2. standaardcomponent hergebruiken;
3. afwijkingen alleen met expliciete reden;
4. PO-test uitbreiden met een UI-conformiteitscheck.
