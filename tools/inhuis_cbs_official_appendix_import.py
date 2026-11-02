"""Import all five official CBS ECOICOPv2 2026 Excel tabs as raw, traceable source cells.

Not a product classification or hierarchy importer: those require independent
verification. No database access, product writes, or inferred parents.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import zipfile

SOURCE_URL = "https://www.cbs.nl/-/media/_excel/2026/04/bijlageecoicopv2indeling.xlsx"
SOURCE_SHA256 = "6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f"
TABS = ("Toelichting", "1-ECOICOPv2", "2-Lijst-Speciale-Aggregaten", "3-SA-CPI-2025=100", "4-SA-HICP-2025=100")
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _cell_value(cell, shared):
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(X + "t"))
    v, f = cell.find(X + "v"), cell.find(X + "f")
    if v is None and f is None:
        return None
    raw = v.text if v is not None else None
    if kind == "s":
        return shared[int(raw or "0")]
    if f is not None:
        return {"formula": f.text or "", "cached": raw}
    return raw


def extract(path):
    original = Path(path).read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"CBS Excel SHA-256 does not match official pinned source: {digest}")
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {e.get("Id"): e.get("Target") for e in relations}
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in item.iter(X + "t"))
                      for item in strings.findall(X + "si")]
        sheets = []
        for sheet in workbook.find(X + "sheets"):
            target = targets[sheet.get(R + "id")]
            name = target.lstrip("/") if target.startswith("/") else "xl/" + target
            name = re.sub(r"/+", "/", name)
            xml = ET.fromstring(archive.read(name))
            rows = []
            for row in xml.findall(".//" + X + "sheetData/" + X + "row"):
                cells = []
                for cell in row.findall(X + "c"):
                    value = _cell_value(cell, shared)
                    if value is not None:
                        cells.append({"address": cell.get("r"), "value": value,
                                      "style": cell.get("s", "")})
                if cells:
                    rows.append({"row": int(row.get("r")), "cells": cells})
            sheets.append({"name": sheet.get("name"), "rows": rows,
                           "nonempty_rows": len(rows),
                           "nonempty_cells": sum(len(r["cells"]) for r in rows)})
    names = tuple(s["name"] for s in sheets)
    if names != TABS:
        raise ValueError(f"CBS five source sheets do not match official order: {names}")
    # The official introduction sheet may carry only formatting, drawings or
    # notes outside sheetData. Preserve it in the original XLSX artifact and
    # report zero cells rather than misclassifying the source as incomplete.
    if any(not s["rows"] for s in sheets if s["name"] != "Toelichting"):
        raise ValueError("Incomplete CBS appendix: an ECOICOP/aggregate data tab is empty")
    return {"source_url": SOURCE_URL, "source_sha256": digest,
            "reference_version": "CBS-ECOICOPv2-2026",
            "representation": "all non-empty source cells, NOT operational categories",
            "sheets": sheets}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    result = extract(a.xlsx)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for sheet in result["sheets"]:
        print("CBS_FULL_SOURCE_TAB", sheet["name"], sheet["nonempty_rows"], sheet["nonempty_cells"])


if __name__ == "__main__":
    main()
