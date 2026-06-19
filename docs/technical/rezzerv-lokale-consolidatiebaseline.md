# Rezzerv lokale consolidatiebaseline

## Doel

Deze branch is aangemaakt om de lokaal geteste PO-versie van Rezzerv gecontroleerd op te schonen en later veilig richting main te brengen.

## Bronbasis

branch: local/consolidatie-po-baseline
afkomstig van: fix/m2c2i-2a-kassa-duplicate-overlay

## Werkwijze

1. De lokaal werkende PO-versie blijft functioneel leidend.
2. Main wordt alleen gebruikt als aanvullende wijzigingsbron.
3. Bestanden worden batchgewijs opgeschoond of aangepast.
4. Na elke functionele batch volgt een lokale test.
5. Er wordt niet rechtstreeks naar main gepusht.

## Beschermde functionaliteit

- Kassa
- Uitpakken
- Externe databases
- Lidl-taxonomiepreview
- lokale externe productindex
- kandidaatopslag zonder automatische definitieve productkoppeling

## Niet meenemen in de schone hoofdversie

- back-ups
- tijdelijke patchscripts
- OCR-debuguitvoer
- diagnosebestanden
- dubbele of dode technische sporen
- lokale runtimebestanden
