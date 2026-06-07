"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from sqlalchemy import text

from app.db import engine
from app.services.receipt_service import _resolve_reparse_source_payload
from app.receipt_ingestion.service_parts.image_ocr_flow import (
    _get_paddle_ocr,
    _extract_payload_from_paddle_item,
    _normalize_paddle_collection,
)

RID = "4ebdf7bf8a344093b6232ec5dd05b3c9"
OUT = Path("/tmp/rezzerv_raw_ocr_diagnostics/r9_38b13/plus_photo2_ocr_fragments.json")
AMOUNT_RE = re.compile(r"[€CE]?-?\d{1,6}(?:[.,]\d{2})", re.I)

CLUSTER_KEYS = {
    "BIO_DADELTJES_RIJSTWAFEL": ["bio", "dadel", "rijst", "wafel", "riust"],
    "MELTY_VEGGIE_LAMA_PUFFS": ["melty", "nelty", "veggie", "lama", "puffs", "pizza"],
    "CARROTS_APPLES_MANGO": ["carrot", "apple", "apples", "mango", "peach"],
    "APPLE_QUINOA_GROENTE_RINGEN": ["quinoa", "groente", "ringen", "12m", "124"],
}

def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()

def payloads(result):
    out = []
    for item in _normalize_paddle_collection(result):
        p = _extract_payload_from_paddle_item(item)
        out.append(p)
    return out

def boxinfo(box):
    if box is None:
        return {}
    try:
        if len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = [float(x) for x in box]
            return {"min_x": min(x1,x2), "max_x": max(x1,x2), "min_y": min(y1,y2), "max_y": max(y1,y2), "center_x": (x1+x2)/2, "center_y": (y1+y2)/2}
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return {"min_x": min(xs), "max_x": max(xs), "min_y": min(ys), "max_y": max(ys), "center_x": (min(xs)+max(xs))/2, "center_y": (min(ys)+max(ys))/2}
    except Exception:
        return {}

def run_ocr(model, b, filename):
    suffix = Path(filename).suffix.lower() or ".jpg"
    with tempfile.TemporaryDirectory(prefix="r9-38b13-") as d:
        p = Path(d) / ("image" + suffix)
        p.write_bytes(b)
        result = model.predict(str(p))
    frags = []
    for pay in payloads(result):
        texts = _normalize_paddle_collection(pay.get("rec_texts") or pay.get("texts"))
        scores = _normalize_paddle_collection(pay.get("rec_scores") or pay.get("scores"))
        boxes = pay.get("rec_boxes")
        if boxes is None:
            boxes = pay.get("dt_polys")
        if boxes is None:
            boxes = pay.get("rec_polys")
        if boxes is None:
            boxes = []
        boxes = _normalize_paddle_collection(boxes)
        for i, t in enumerate(texts):
            s = scores[i] if i < len(scores) else None
            box = boxes[i] if i < len(boxes) else None
            txt = norm(t)
            if not txt:
                continue
            bi = boxinfo(box)
            frags.append({
                "i": len(frags),
                "text": txt,
                "amounts": AMOUNT_RE.findall(txt),
                "score": float(s) if s is not None else None,
                **bi,
            })
    return sorted(frags, key=lambda r: (r.get("center_y", 0), r.get("center_x", 0)))

def near_clusters(frags):
    result = {}
    for name, keys in CLUSTER_KEYS.items():
        hits = []
        for f in frags:
            tx = f["text"].lower()
            if any(k in tx for k in keys):
                hits.append(f)
        if hits:
            ys = [h.get("center_y", 0) for h in hits]
            ymin, ymax = min(ys) - 80, max(ys) + 80
            result[name] = [f for f in frags if ymin <= f.get("center_y", 0) <= ymax]
        else:
            result[name] = []
    return result

with engine.connect() as conn:
    rec = conn.execute(text("""
        SELECT rr.id AS raw_receipt_id, rr.original_filename, rr.mime_type,
               rr.storage_path, rt.id AS receipt_table_id, rem.body_html,
               rem.body_text, rem.selected_part_type
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
        WHERE rt.id=:rid
        LIMIT 1
    """), {"rid": RID}).mappings().first()
    rows = conn.execute(text("""
        SELECT line_index, raw_label, normalized_label, line_total, discount_amount, unit_price, quantity
        FROM receipt_table_lines
        WHERE receipt_table_id=:rid
        ORDER BY line_index, id
    """), {"rid": RID}).mappings().all()

rec = dict(rec)
raw = Path(rec["storage_path"]).read_bytes()
parse_bytes, parse_filename, parse_mime = _resolve_reparse_source_payload(rec, raw)

model = _get_paddle_ocr()
runtime_frags = run_ocr(model, parse_bytes, parse_filename or rec["original_filename"])

report = {
    "test": "R9-38B13 PLUS photo 2 raw/preprocessed OCR fragment analysis",
    "read_only": True,
    "database_write_intent": False,
    "parser_write_intent": False,
    "target": {
        "receipt_table_id": RID,
        "original_filename": rec["original_filename"],
        "parse_filename": parse_filename,
        "parse_mime": parse_mime,
    },
    "stored_db_lines": [dict(r) for r in rows],
    "runtime_fragment_count": len(runtime_frags),
    "runtime_fragments": runtime_frags,
    "focus_clusters_runtime": near_clusters(runtime_frags),
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

print(json.dumps({
    "status": "ok",
    "output_json_path": str(OUT),
    "runtime_fragment_count": len(runtime_frags),
    "focus_cluster_counts": {k: len(v) for k, v in report["focus_clusters_runtime"].items()},
}, indent=2, ensure_ascii=False))
