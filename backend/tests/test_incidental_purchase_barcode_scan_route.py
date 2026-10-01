from pathlib import Path
import re


def test_incidental_purchase_barcode_scan_route_is_registered():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")

    assert re.search(
        r'@app\.post\("/api/articles/barcode-scan"\)\s+'
        r'def scan_article_barcode\(',
        source,
    ), "POST /api/articles/barcode-scan moet scan_article_barcode registreren"
