"""Download and compare official English and Dutch GPC publications."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from app.services.gpc_official_translation_source import download_official_gpc_translation_sync

ENTITY_TAGS = {
    "segment": "segment",
    "family": "family",
    "class": "class",
    "brick": "brick",
    "attribute_type": "attType",
    "attribute_value": "attValue",
}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extract_names(xml_path: str | Path) -> dict[str, dict[str, str]]:
    root = ET.parse(xml_path).getroot()
    result = {entity: {} for entity in ENTITY_TAGS}
    reverse = {tag: entity for entity, tag in ENTITY_TAGS.items()}
    for element in root.iter():
        entity = reverse.get(_local_name(element.tag))
        if not entity:
            continue
        code = (element.get("code") or "").strip()
        text = (element.get("text") or "").strip()
        if code and text:
            result[entity][code] = text
    return result


def compare_publications(english_xml: str | Path, dutch_xml: str | Path) -> dict:
    english = extract_names(english_xml)
    dutch = extract_names(dutch_xml)
    by_type = {}
    missing_rows = []
    for entity in ENTITY_TAGS:
        en_codes = set(english[entity])
        nl_codes = set(dutch[entity])
        missing = sorted(en_codes - nl_codes)
        extra = sorted(nl_codes - en_codes)
        blank = sorted(code for code in en_codes & nl_codes if not dutch[entity][code].strip())
        identical = sorted(code for code in en_codes & nl_codes if english[entity][code] == dutch[entity][code])
        by_type[entity] = {
            "english": len(en_codes),
            "dutch": len(nl_codes),
            "missing_in_dutch": len(missing),
            "extra_in_dutch": len(extra),
            "blank_dutch": len(blank),
            "identical_text": len(identical),
        }
        for code in missing:
            missing_rows.append({"entity_type": entity, "entity_code": code, "english_text": english[entity][code]})
    return {
        "status": "complete" if not missing_rows else "incomplete",
        "by_entity_type": by_type,
        "missing_total": len(missing_rows),
        "missing": missing_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vergelijk live Engelse en Nederlandse GS1 GPC-publicaties.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output = Path(args.output_dir)
    en = download_official_gpc_translation_sync(output / "en", language_code="en", file_format="xml")
    nl = download_official_gpc_translation_sync(output / "nl", language_code="nl", file_format="xml")
    report = compare_publications(en["file_path"], nl["file_path"])
    report["english_source"] = en
    report["dutch_source"] = nl
    report_path = output / "gpc-en-nl-validation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    missing_path = output / "gpc-missing-dutch.csv"
    with missing_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("entity_type", "entity_code", "english_text"))
        writer.writeheader()
        writer.writerows(report["missing"])
    print(json.dumps({**report, "report_path": str(report_path), "missing_path": str(missing_path)}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "complete" else 3


if __name__ == "__main__":
    raise SystemExit(main())
