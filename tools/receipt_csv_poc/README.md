# Standalone Receipt Photo to CSV POC

Deze map bevat een **losse Python proof-of-concept** om foto’s van supermarkt-kassabonnen onafhankelijk van Rezzerv in te lezen en om te zetten naar CSV.

De POC raakt geen Rezzerv-runtimecode. De invoer en uitvoer zitten volledig binnen deze map.

## Doel

- Foto's of scans van kassabonnen verwerken met lokale OCR.
- Per bon regels herkennen met artikelnaam en bedrag.
- Per bon een CSV-bestand maken.
- Alle gevonden regels combineren in één `combined_receipts.csv`.
- OCR-tekst en parse-waarschuwingen bewaren voor analyse.

## Vereisten

1. Python 3.11 of nieuwer.
2. Tesseract OCR geïnstalleerd op de machine.
3. Optioneel maar aanbevolen: Nederlandse Tesseract-taaldata (`nld`).

Controleer lokaal:

```bash
tesseract --version
tesseract --list-langs
```

## Installatie

Vanuit deze map:

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows PowerShell/CMD
# of: source .venv/bin/activate op Linux/macOS
pip install -r requirements.txt
```

## Gebruik

1. Zet kassabonfoto’s in:

```text
tools/receipt_csv_poc/input_receipts/
```

Ondersteunde extensies: `.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`, `.tiff`, `.bmp`.

2. Draai:

```bash
python receipt_to_csv.py --input input_receipts --output output_csv --lang nld+eng
```

Als Nederlandse OCR-data ontbreekt:

```bash
python receipt_to_csv.py --input input_receipts --output output_csv --lang eng
```

## Output

```text
output_csv/
  combined_receipts.csv
  processing_report.csv
  ocr_text/
    <bonnaam>.txt
  per_receipt/
    <bonnaam>.csv
  debug_images/
    <bonnaam>_gray.png
    <bonnaam>_threshold.png
```

## CSV-kolommen

`combined_receipts.csv` bevat:

- `source_file`
- `line_no`
- `item_text`
- `quantity`
- `unit_price`
- `line_total`
- `currency`
- `parser_confidence`
- `raw_line`
- `warning`

## Parserstrategie

Deze POC gebruikt bewust een generieke aanpak:

1. Beeldvoorbewerking met OpenCV.
2. OCR via Tesseract.
3. Regels zoeken waarin rechts een bedrag staat.
4. Niet-artikelregels uitsluiten, zoals `TOTAAL`, `SUBTOTAAL`, `BTW`, `PIN`, `VISA`, `WISSELGELD`.
5. Productnaam en bedrag scheiden.
6. CSV schrijven.

## Belangrijk

Dit is een zelfstandige POC. De kwaliteit hangt sterk af van:

- scherpte van de foto;
- perspectief/cropping;
- licht/schaduw;
- beschikbare Tesseract-taaldata;
- supermarkt-specifieke kassabonlayout.

De bedoeling is om hiermee eerst objectief te meten welke bonnen generiek goed gaan en waar winkel-specifieke regels nodig zijn.