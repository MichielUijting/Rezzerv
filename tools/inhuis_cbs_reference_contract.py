"""Fail-closed cross-validation of bundled CBS authority against the signed official Excel extraction.

The pinned XLSX is the truth for every code, Dutch label, row number and
official 'Laagste groep' (J/N). Parentage is independently cross-checked
against complete-level structure and leaf evidence, never used as a guess.
Does not connect to or mutate any database.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

SHA = "6871458274be87aa0126eab1bf334365502438f5e976845df8e5c28cdf95858f"
VERSION = "CBS-ECOICOPv2-2026"
LEVELS = {1: 15, 2: 59, 3: 134, 4: 224, 5: 8}
SHEETS = (
    "Toelichting", "1-ECOICOPv2", "2-Lijst-Speciale-Aggregaten",
    "3-SA-CPI-2025=100", "4-SA-HICP-2025=100",
)


def _cell_map(row: dict) -> dict[str, str]:
    return {re.match(r"[A-Z]+", cell["address"]).group(): str(cell["value"]).strip()
            for cell in row["cells"]}


def validate_official_reference(bundled: dict, official: dict) -> dict:
    if official.get("source_sha256") != SHA or bundled.get("source_sha256") != SHA:
        raise ValueError("Officiële CBS-bron SHA-256 komt niet overeen.")
    if bundled.get("reference_version") != VERSION:
        raise ValueError("CBS-referentieversie wijkt af.")
    sheets = official.get("sheets", [])
    if tuple(s.get("name") for s in sheets) != SHEETS:
        raise ValueError("CBS-bron bevat niet de vijf officiële tabbladen.")
    if any(not s.get("rows") for s in sheets[1:]):
        raise ValueError("Officieel CBS-datatabblad is leeg.")
    original_rows = sheets[1]["rows"]
    if len(original_rows) != 441:
        raise ValueError("Officiële classificatie moet een kopregel en 440 rijen bevatten.")
    header = _cell_map(original_rows[0])
    if header.get("A") != "ECOICOPv2 nummer" or header.get("B") != "Omschrijving" or not header.get("F", "").startswith("Laagste ECOICOPv2"):
        raise ValueError("CBS-Excelkolommen zijn gewijzigd.")
    entries = bundled.get("categories", [])
    if len(entries) != 440:
        raise ValueError("CBS-referentie is niet volledig (440 categorieën vereist).")
    keys = [entry.get("cbs_code") for entry in entries]
    if len(set(keys)) != 440:
        raise ValueError("Dubbele CBS-categorieën.")
    by_code = dict(zip(keys, entries))
    parents = set()
    levels = Counter()
    skipped_class_parents = {'023000', '054000', '101000', '105000', '112000', '133000', '139000'}
    verified_skips = []
    for i, (row, entry) in enumerate(zip(original_rows[1:], entries)):
        fields = _cell_map(row)
        code, name = fields.get("A"), fields.get("B")
        if not re.fullmatch(r"[0-9]{6}", code or ""):
            raise ValueError(f"Geen geldige CBS-code op Excelrij {row['row']}.")
        if (entry.get("source_excel_row") != row["row"] or entry.get("cbs_code") != code
                or entry.get("name_nl") != name):
            raise ValueError(f"CBS-categorie op rij {row['row']} wijkt af van officiële bijlage.")
        if fields.get("F") not in {"J", "N"}:
            raise ValueError(f"Officiële laagste-groep-markering op {code} ontbreekt.")
        if entry.get("lowest") is not (fields["F"] == "J"):
            raise ValueError(f"Officiële laagste-groep-markering {code} is onjuist.")
        level, parent = entry.get("level"), entry.get("parent_code")
        if type(level) is not int or level not in LEVELS:
            raise ValueError(f"Ongeldig niveau voor {code}.")
        if (parent is None) != (level == 1):
            raise ValueError(f"Ongeldige ouder voor {code}.")
        if parent is not None:
            candidate = by_code.get(parent)
            if not candidate:
                raise ValueError(f"Ontbrekende ouder {parent} van {code}.")
            gap = level - candidate["level"]
            if gap == 2 and parent in skipped_class_parents:
                verified_skips.append(parent)
            elif gap != 1:
                raise ValueError(f"Onjuiste officiële ouderrelatie {parent} van {code}.")
            if candidate.get("source_excel_row", 99999) >= row["row"]:
                raise ValueError(f"Parent {parent} staat niet vóór kind {code} in CBS-bron.")
            parents.add(parent)
        levels[level] += 1
    if dict(levels) != LEVELS:
        raise ValueError(f"Officiële CBS-niveaus wijken af: {dict(levels)}.")
    for entry in entries:
        if (entry["cbs_code"] not in parents) != entry["lowest"]:
            raise ValueError(f"CBS-laagste-groep en feitelijke kinderen wijken af: {entry['cbs_code']}")
    if len(parents) != 126:
        raise ValueError("Officiële CBS-hiërarchie verwacht 126 oudercategorieën.")
    if len(verified_skips) != 22 or set(verified_skips) != skipped_class_parents:
        raise ValueError("22 officiële CBS-categorieën met overgeslagen tussenniveau wijken af.")
    if by_code["011221"]["parent_code"] != "011220" or by_code["011420"]["parent_code"] != "011400":
        raise ValueError("CBS-microklasse of melkhiërarchie wijkt af.")
    return {"categories": len(entries), "levels": dict(levels),
            "lowest": sum(e["lowest"] for e in entries), "source_sha256": SHA}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-source", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    args = parser.parse_args()
    official = json.loads(args.official_source.read_text(encoding="utf-8"))
    bundled = json.loads(args.reference.read_text(encoding="utf-8"))
    proof = validate_official_reference(bundled, official)
    print("CBS_OFFICIAL_HIERARCHY_VERIFIED", json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
