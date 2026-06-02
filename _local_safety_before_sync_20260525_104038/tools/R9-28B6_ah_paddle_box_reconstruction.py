from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:[,.]\d{2})$")
QTY_RE = re.compile(r"^\d+(?:[,.]\d{1,3})?$")

HEADER_WORDS = {"aantal", "omschrijving", "prijs", "bedrag"}
PAYMENT_WORDS = {
    "betaald", "met", "pinnen", "pin", "poi", "terminal", "merchant", "transactie",
    "kaart", "kaartserienummer", "betaling", "autorisatiecode", "leesmethode",
    "nfc", "chip", "vpay", "v-pay", "maestro", "contactless", "periode", "token",
}
TAX_WORDS = {"btw", "over", "eur", "9%", "21%", "vat"}
TOTAL_WORDS = {"totaal", "subtotaal", "betalen", "te betalen"}
DISCOUNT_WORDS = {"bonus", "bbox", "voordeel", "korting", "waarvan", "app deals"}
LOYALTY_WORDS = {"koopzegels", "koopzegel", "spaarzegels", "espaazegels", "miles", "airmiles"}


@dataclass
class BoxItem:
    index: int
    text: str
    confidence: float | None
    bbox: list[float] | None
    x1: float
    y1: float
    x2: float
    y2: float
    cx: float
    cy: float
    w: float
    h: float
    section_type: str
    column_role: str


@dataclass
class ReconstructedArticle:
    article_name: str
    amount: float | None
    amount_text: str | None
    name_item_indexes: list[int]
    amount_item_index: int | None
    confidence_min: float | None
    y_center: float
    rule_id: str
    reason: str


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def is_amount(text: str) -> bool:
    return bool(AMOUNT_RE.match(str(text or "").strip()))


def to_amount(text: str) -> float | None:
    if not is_amount(text):
        return None
    try:
        return float(str(text).replace(",", "."))
    except Exception:
        return None


def is_qty(text: str) -> bool:
    return bool(QTY_RE.match(str(text or "").strip())) and not is_amount(text)


def safe_bbox(raw: Any) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    try:
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        if isinstance(raw, (list, tuple)) and len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw):
            x1, y1, x2, y2 = [float(v) for v in raw]
            return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
        # Polygon-like [[x,y], ...]
        if isinstance(raw, (list, tuple)):
            pts = []
            for p in raw:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return None
    return None


def classify_section(text: str) -> str:
    n = norm(text)
    tokens = set(re.findall(r"[a-zA-Z0-9%\-]+", n))
    if n in HEADER_WORDS or any(w in n for w in HEADER_WORDS):
        return "AH_COLUMN_HEADER"
    if any(w in n for w in PAYMENT_WORDS):
        return "AH_PAYMENT"
    if any(w in n for w in TAX_WORDS):
        return "AH_TAX"
    if "te betalen" in n or n in TOTAL_WORDS or any(w in n for w in TOTAL_WORDS):
        return "AH_TOTAL_OR_SUBTOTAL"
    if any(w in n for w in DISCOUNT_WORDS):
        return "AH_DISCOUNT"
    if any(w in n for w in LOYALTY_WORDS):
        return "AH_LOYALTY"
    if "albert" in n or "telefoon" in n or "station" in n:
        return "AH_HEADER"
    if "download" in n or "gratis" in n or "spaar automatisch" in n:
        return "AH_FOOTER"
    return "AH_UNKNOWN"


def column_role_from_position(item: BoxItem, anchors: dict[str, float]) -> str:
    if is_qty(item.text):
        return "quantity"
    if is_amount(item.text):
        if item.cx >= anchors.get("amount_min_x", 0):
            return "amount"
        return "price"
    n = norm(item.text)
    if n in HEADER_WORDS:
        return "column_header"
    if item.cx < anchors.get("description_min_x", 0):
        return "quantity_or_left_margin"
    if item.cx >= anchors.get("amount_min_x", 0):
        return "amount_text_or_right_margin"
    return "description"


def load_report(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError("R9-28B6 verwacht de R9-28B5 JSON-output, niet het MD-bestand.")


def build_items(report: dict[str, Any]) -> list[BoxItem]:
    out = []
    for raw in report.get("paddle", {}).get("items", []) or []:
        bbox = safe_bbox(raw.get("bbox"))
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        text = str(raw.get("text") or "").strip()
        section = classify_section(text)
        out.append(BoxItem(
            index=int(raw.get("index") or 0),
            text=text,
            confidence=raw.get("confidence"),
            bbox=[x1, y1, x2, y2],
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            cx=(x1+x2)/2,
            cy=(y1+y2)/2,
            w=x2-x1,
            h=y2-y1,
            section_type=section,
            column_role="unknown",
        ))
    return sorted(out, key=lambda i: (i.cy, i.x1))


def derive_anchors(items: list[BoxItem]) -> dict[str, float]:
    anchors: dict[str, float] = {}
    for item in items:
        n = norm(item.text)
        if n == "aantal":
            anchors["quantity_x"] = item.cx
        elif n == "omschrijving":
            anchors["description_x"] = item.cx
            anchors["description_min_x"] = max(0.0, item.x1 - 50)
        elif n == "prijs":
            anchors["price_x"] = item.cx
        elif n == "bedrag":
            anchors["amount_x"] = item.cx
            anchors["amount_min_x"] = max(0.0, item.x1 - 80)
    if "description_min_x" not in anchors:
        anchors["description_min_x"] = 350.0
    if "amount_min_x" not in anchors:
        amount_items = [i for i in items if is_amount(i.text)]
        anchors["amount_min_x"] = sorted([i.cx for i in amount_items])[-1] - 150 if amount_items else 900.0
    return anchors


def find_article_band(items: list[BoxItem]) -> tuple[float, float]:
    header_y = None
    for item in items:
        if norm(item.text) == "omschrijving":
            header_y = item.cy
            break
    if header_y is None:
        header_y = min((i.cy for i in items), default=0)

    stop_candidates = [
        i.cy for i in items
        if classify_section(i.text) in {"AH_TOTAL_OR_SUBTOTAL", "AH_DISCOUNT", "AH_PAYMENT", "AH_TAX", "AH_FOOTER"}
        and i.cy > header_y
    ]
    stop_y = min(stop_candidates) if stop_candidates else max((i.cy for i in items), default=header_y)
    return header_y + 20, stop_y - 5


def pair_articles(items: list[BoxItem], anchors: dict[str, float], band: tuple[float, float]) -> list[ReconstructedArticle]:
    y_min, y_max = band
    candidates = [
        i for i in items
        if y_min <= i.cy <= y_max
        and i.section_type == "AH_UNKNOWN"
        and not norm(i.text) in HEADER_WORDS
    ]

    desc_items = [
        i for i in candidates
        if not is_amount(i.text)
        and not is_qty(i.text)
        and anchors["description_min_x"] <= i.cx < anchors["amount_min_x"]
        and len(re.findall(r"[a-zA-ZÀ-ÿ]", i.text)) >= 2
    ]

    amount_items = [
        i for i in candidates
        if is_amount(i.text)
        and i.cx >= anchors["amount_min_x"]
    ]

    articles: list[ReconstructedArticle] = []
    used_amounts: set[int] = set()

    for desc in sorted(desc_items, key=lambda i: (i.cy, i.x1)):
        nearby = [
            a for a in amount_items
            if a.index not in used_amounts and abs(a.cy - desc.cy) <= max(90.0, desc.h * 1.2)
        ]
        if not nearby:
            # In AH foto 3 the first article amount is one line above due skew/grouping.
            nearby = [
                a for a in amount_items
                if a.index not in used_amounts and 0 <= desc.cy - a.cy <= 180
            ]
        if not nearby:
            continue
        amount_item = sorted(nearby, key=lambda a: (abs(a.cy - desc.cy), a.x1))[0]
        used_amounts.add(amount_item.index)
        confs = [v for v in [desc.confidence, amount_item.confidence] if isinstance(v, (int, float))]
        articles.append(ReconstructedArticle(
            article_name=desc.text,
            amount=to_amount(amount_item.text),
            amount_text=amount_item.text,
            name_item_indexes=[desc.index],
            amount_item_index=amount_item.index,
            confidence_min=min(confs) if confs else None,
            y_center=(desc.cy + amount_item.cy)/2,
            rule_id="AH_PADDLE_BOX_DESCRIPTION_AMOUNT_PAIR_RULE",
            reason="Omschrijving-item in artikelband gekoppeld aan rechter bedrag-item via bounding-box y/x positie.",
        ))

    return articles


def blocked_items(items: list[BoxItem]) -> list[dict[str, Any]]:
    blocked_sections = {
        "AH_COLUMN_HEADER",
        "AH_PAYMENT",
        "AH_TAX",
        "AH_TOTAL_OR_SUBTOTAL",
        "AH_DISCOUNT",
        "AH_LOYALTY",
        "AH_HEADER",
        "AH_FOOTER",
    }
    return [
        {
            "index": i.index,
            "text": i.text,
            "section_type": i.section_type,
            "bbox": i.bbox,
            "reason": "Niet-artikel sectie volgens AH Paddle-box section classifier.",
        }
        for i in items
        if i.section_type in blocked_sections
    ]


def build_report(input_json: Path) -> dict[str, Any]:
    source = load_report(input_json)
    items = build_items(source)
    anchors = derive_anchors(items)
    for item in items:
        item.column_role = column_role_from_position(item, anchors)
    band = find_article_band(items)
    articles = pair_articles(items, anchors, band)

    return {
        "audit": "R9-28B6 AH Paddle-box section and column reconstruction",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "diagnostic only; no parser/OCR/database/status/baseline/UI mutation",
        "ssot_compliance": {
            "status_determination": "not_performed",
            "status_service": "receipt_status_baseline_service_v4.py",
            "parse_status_used_as_truth": False,
            "parser_mutated": False,
            "ocr_mutated": False,
            "database_mutated": False,
            "baseline_mutated": False,
            "ui_touched": False,
            "diagnostics_promoted_to_parser": False,
        },
        "source_report": str(input_json),
        "input": source.get("input", {}),
        "anchors": anchors,
        "article_band": {"y_min": band[0], "y_max": band[1]},
        "summary": {
            "paddle_item_count": len(items),
            "blocked_non_article_count": len(blocked_items(items)),
            "reconstructed_article_count": len(articles),
            "reconstructed_article_sum": round(sum(a.amount or 0 for a in articles), 2),
        },
        "reconstructed_articles": [asdict(a) for a in articles],
        "blocked_non_article_items": blocked_items(items),
        "classified_items": [asdict(i) for i in items],
        "next_step_hint": "Use this diagnostic result to validate AH chain rules across all AH receipts before touching runtime parser logic.",
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# R9-28B6 — AH Paddle-box section and column reconstruction",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-compliance",
        "",
    ]
    for k, v in report["ssot_compliance"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Samenvatting",
        "",
    ]
    for k, v in report["summary"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += [
        "",
        "## Gereconstrueerde artikelregels",
        "",
    ]
    for a in report["reconstructed_articles"]:
        lines.append(f"- `{a['article_name']}` — `{a['amount_text']}` — rule `{a['rule_id']}`")
    lines += [
        "",
        "## Geblokkeerde niet-artikelitems",
        "",
    ]
    for b in report["blocked_non_article_items"]:
        lines.append(f"- `{b['text']}` → `{b['section_type']}`")
    lines += [
        "",
        "## Kolomankers",
        "",
        "```json",
        json.dumps(report["anchors"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Vervolg",
        "",
        report["next_step_hint"],
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("r9_28b5_json", help="R9-28B5 JSON report")
    parser.add_argument("--out", default="/tmp/R9-28B6_ah_reconstruction")
    args = parser.parse_args()

    input_json = Path(args.r9_28b5_json)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(input_json)
    filename = report.get("input", {}).get("filename") or "receipt"
    safe_name = Path(filename).stem.replace(" ", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"R9-28B6_ah_paddle_box_reconstruction_{safe_name}_{stamp}.json"
    md_path = out_dir / f"R9-28B6_ah_paddle_box_reconstruction_{safe_name}_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_md(report), encoding="utf-8")

    print("R9-28B6 AH Paddle-box reconstruction geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    print(f"reconstructed_article_count={report['summary']['reconstructed_article_count']}")
    print(f"reconstructed_article_sum={report['summary']['reconstructed_article_sum']}")
    for a in report["reconstructed_articles"]:
        print(f"- {a['article_name']} | {a['amount_text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
