# MeesdeBoer scanner-engine (Inhuis-owned)

Broncode overgenomen uit `Meesdeboer/in-huis-demo`, branch `master`, bron-ZIP aangeleverd door de PO op 14 oktober 2026. De PO bevestigt toestemming van de oorspronkelijke auteur om deze code in de eigen repository op te nemen. De schriftelijke omvang van verdere redistributierechten moet nog worden gedocumenteerd voordat publieke distributie plaatsvindt.

Scanner-engine: `scan_engine.py`, SHA256 `e37877be796bac594940fcaa6ac976b86281ec3f77f9cf8b070b826c077319f6` (originele bytes ongewijzigd). Runtime-eisen: `requirements.txt`, Python >=3.11, DocAligner-modeldownload, Anthropic API-sleutel en Anthropic-service. Geen tweede database, accountsysteem, migraties of losse scan-UI uit het bronproject overgenomen.

Inhuis' bestaande `inhuis_demo_bridge.py` en `start-alternatieve-kassabonscanner.bat` gebruiken voortaan dit repository-eigen pakket. De scanneromgeving is een niet-geversioneerde venv onder `tools/receipt_scanner/.venv`. De Anthropic-sleutel blijft uitsluitend in de lokale niet-geversioneerde root `.env` als `ANTHROPIC_API_KEY`; het bestand wordt nooit gecommit. Bestaande externe `.env`-sleutels worden niet automatisch gelezen, gekopieerd of gepubliceerd.

Geen uitvoering van de officiële `start.bat` tijdens deze broncode-import; een aparte lokale functionele test blijft vereist. De bestaande buitenstaande poort-8003-listener wordt nooit automatisch gestopt of vervangen.