"""Build a compact Dutch GPC reference file from an official GS1 XML publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _code(element: ET.Element) -> str:
    return str(element.get("code") or "").strip()


def _text(element: ET.Element) -> str:
    return str(element.get("text") or "").strip()


def build_reference(xml_path: str | Path) -> list[dict[str, str]]:
    root = ET.parse(xml_path).getroot()
    rows: list[dict[str, str]] = []

    def walk(
        element: ET.Element,
        *,
        segment: tuple[str, str] = ("", ""),
        family: tuple[str, str] = ("", ""),
        class_item: tuple[str, str] = ("", ""),
    ) -> None:
        name = _local_name(element.tag)
        current_segment = segment
        current_family = family
        current_class = class_item

        if name == "segment":
            current_segment = (_code(element), _text(element))
        elif name == "family":
            current_family = (_code(element), _text(element))
        elif name == "class":
            current_class = (_code(element), _text(element))
        elif name == "brick":
            brick_code = _code(element)
            brick_name = _text(element)
            if brick_code and brick_name:
                rows.append({
                    "gpc_brick_code": brick_code,
                    "gpc_brick_name": brick_name,
                    "gpc_class_code": current_class[0],
                    "gpc_class_name": current_class[1],
                    "gpc_family_code": current_family[0],
                    "gpc_family_name": current_family[1],
                    "gpc_segment_code": current_segment[0],
                    "gpc_segment_name": current_segment[1],
                })

        for child in list(element):
            walk(
                child,
                segment=current_segment,
                family=current_family,
                class_item=current_class,
            )

    walk(root)
    deduplicated = {
        row["gpc_brick_code"]: row
        for row in rows
        if row["gpc_brick_code"]
    }
    return [deduplicated[code] for code in sorted(deduplicated)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bouw de compacte Nederlandse GPC Brick/Familie-referentie."
    )
    parser.add_argument("--xml", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--publication-version", default="")
    args = parser.parse_args(argv)

    rows = build_reference(args.xml)
    if not rows:
        raise RuntimeError("De Nederlandse GS1-publicatie bevat geen bruikbare Brick-records")

    incomplete = [
        row["gpc_brick_code"]
        for row in rows
        if not all((
            row["gpc_brick_name"],
            row["gpc_class_code"],
            row["gpc_class_name"],
            row["gpc_family_code"],
            row["gpc_family_name"],
            row["gpc_segment_code"],
            row["gpc_segment_name"],
        ))
    ]
    if incomplete:
        raise RuntimeError(
            f"Nederlandse GPC-hiërarchie is onvolledig voor {len(incomplete)} Bricks"
        )

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": "GS1 GPC Browser",
        "language_code": "nl",
        "publication_version": str(args.publication_version or "").strip(),
        "brick_count": len(rows),
        "bricks": rows,
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "ok": True,
        "output": str(target),
        "brick_count": len(rows),
        "family_count": len({row["gpc_family_code"] for row in rows}),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
