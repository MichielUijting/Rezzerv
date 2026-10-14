# Inhuis AI-kassabonscanner — eigen bronbeheer

De scannerbron is door de PO, met toestemming van de oorspronkelijke maker
MeesdeBoer, overgenomen in `tools/receipt_scanner/meesdeboer_engine/`.
De originele externe Git-repository `Meesdeboer/in-huis-demo` is geen
installatievereiste meer.

## Onderdelen

- `scan_engine.py`: oorspronkelijke bonherkenning, DocAligner-hoekdetectie,
  perspectiefcorrectie, PDF-interpretatie en Claude-gebaseerde extractie.
- `../inhuis_demo_bridge.py`: eigen Inhuis HTTP-interface met servicekey en
  canonieke bonregels voor Kassa.
- `requirements.txt`: vastgelegde Python-dependencies.
- `start-alternatieve-kassabonscanner.bat`: bestaande Inhuis-starter,
  bijgewerkt voor de repository-eigen scannerbron.

## Wat wel en niet zelfstandig is

De **broncode** staat volledig in de Inhuis-repository. De eerste installatie
maakt een lokale Python-omgeving aan en installeert dependencies uit de
Python-package-index. DocAligner laadt een ONNX-model via zijn eigen
pakketfunctionaliteit; offline aanwezigheid of reproduceerbare modeldownload
is nog **niet bewezen**. De Claude API blijft noodzakelijk voor boninterpretatie
en vereist een lokaal ingestelde `ANTHROPIC_API_KEY`. API-keys mogen nooit
worden gecommit. De Inhuis-bridgekey wordt lokaal gegenereerd in `.env`.

Dit is geen toezegging dat een nieuwe installatie zonder netwerkverbinding
kan werken. Voor volledige offline distributie is nog een afzonderlijke
model-/dependencybundel en licentiecontrole nodig.

## Integratie- en kwaliteitscontract

De originele parser levert `kind=product` en `kind=adjustment`.
Artikelgebonden korting staat op `discount_amount`. Losse negatieve
aanpassingen krijgen in Inhuis `line_type=discount`; positieve
aanpassingen krijgen `line_type=fee`. Geen van beide zijn voorraadartikelen.

De nieuwe bridge en de bijbehorende tests zijn in PR #587 opgenomen.
De eerdere, afzonderlijke PR #586 raakt dezelfde bridge: bij merge moet de
definitieve kandidaat op de actuele main worden gecontroleerd op behoud van
beide wijzigingen. Een eenmaal uitgevoerde test op een eerdere SHA is geen
bewijs voor een latere SHA.

## Herkomst en toestemming

Bron: `Meesdeboer/in-huis-demo`, door de PO geëxporteerd als ZIP.
De PO heeft bevestigd toestemming van MeesdeBoer te hebben om de code
volledig in zijn eigen repository op te nemen. De precieze schriftelijke
licentie-/distributievoorwaarden zijn hier niet bijgevoegd. Herdistributie
aan derden dient afzonderlijk tegen die voorwaarden te worden getoetst.
