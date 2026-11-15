"""Verified import of ChatGPT/Excel Catalogus classification proposals.

Preview is read-only. Explicit confirmation is transactional, identity-bound,
permission-gated and never writes unreviewed or unknown classifications.
"""
from __future__ import annotations

import csv
import io
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from sqlalchemy import text

from app.services.catalog_classification_export_service import build_catalog_classification_export
from app.services.cbs_classification_service import confirm_cbs_batch

MAX_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED = 25 * 1024 * 1024
MAX_ROWS = 5000

CSV_FIELDS = (
    "product_id", "name", "brand", "category", "primary_gtin",
    "gpc_bestaand", "gpc_omschrijving_bestaand", "gpc_voorstel",
    "gpc_omschrijving_voorstel", "gpc_status", "gpc_onderbouwing",
    "cbs_bestaand", "cbs_omschrijving_bestaand", "cbs_voorstel",
    "cbs_omschrijving_voorstel", "cbs_status", "cbs_onderbouwing",
    "bevestigde_matches", "synoniemen", "controle_bestaande_code",
    "gpc_controlealternatief", "cbs_controlealternatief", "snapshot_sha256",
)
EXCEL_FIELDS = (
    "Catalogus-ID", "Artikel", "Merk", "OFF-categorie", "GTIN",
    "GS1 bestaand", "GS1 bestaand naam", "GS1 voorstel",
    "GS1 voorstel naam", "GS1 status", "GS1 onderbouwing",
    "CBS bestaand", "CBS bestaand naam", "CBS voorstel",
    "CBS voorstel naam", "CBS status", "CBS onderbouwing",
    "Matches", "Synoniemen", "Bestaand controleren", "GS1 controlecode",
    "CBS controlecode", "Snapshot SHA256",
)
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class ImportContractError(ValueError):
    pass


def _csv_table(data: bytes):
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ImportContractError("CSV moet UTF-8 zijn.") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""), delimiter=";")
    if tuple(reader.fieldnames or ()) != CSV_FIELDS:
        raise ImportContractError("CSV-kolommen wijken af van het Inhuis-classificatiebestand.")
    return [{key: str(record.get(key) or "").strip() for key in CSV_FIELDS}
            for record in reader]


def _column_number(ref):
    result = 0
    for char in re.match(r"^[A-Z]+", ref or "").group(0):
        result = result * 26 + ord(char) - 64
    return result - 1


def _xlsx_table(data: bytes):
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            if len(archive.namelist()) > 80 or sum(x.file_size for x in archive.infolist()) > MAX_UNCOMPRESSED:
                raise ImportContractError("Excelbestand is te groot of bevat te veel onderdelen.")
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall("s:si", NS):
                    shared.append("".join(n.text or "" for n in item.findall(".//s:t", NS)))
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            target_by_id = {x.get("Id"): x.get("Target") for x in rels.findall("p:Relationship", {"p": RELS_NS})}
            sheet = next((x for x in book.findall("s:sheets/s:sheet", NS)
                          if x.get("name") == "Alle artikelen"), None)
            if sheet is None:
                raise ImportContractError("Excel mist tabblad 'Alle artikelen'.")
            target = target_by_id.get(sheet.get("{" + NS["r"] + "}id"), "")
            path = posixpath.normpath(target.lstrip("/") if target.startswith("/xl/") else posixpath.join("xl", target))
            if path.startswith("xl/xl/"):
                path = path[3:]
            if not path.startswith("xl/worksheets/"):
                raise ImportContractError("Ongeldige Excel-werkbladverwijzing.")
            sheet_root = ET.fromstring(archive.read(path))
            matrix = []
            for row in sheet_root.findall(".//s:sheetData/s:row", NS):
                if len(matrix) > MAX_ROWS:
                    raise ImportContractError("Maximaal 5.000 Catalogusartikelen per bestand.")
                cells = [""] * len(EXCEL_FIELDS)
                for cell in row.findall("s:c", NS):
                    if cell.find("s:f", NS) is not None:
                        raise ImportContractError("Excel-formules mogen niet in het importblad staan.")
                    index = _column_number(cell.get("r"))
                    if index >= len(cells):
                        continue
                    value = cell.find("s:v", NS)
                    if cell.get("t") == "inlineStr":
                        text_value = "".join(x.text or "" for x in cell.findall(".//s:t", NS))
                    else:
                        text_value = value.text if value is not None and value.text is not None else ""
                        if cell.get("t") == "s":
                            text_value = shared[int(text_value)]
                    cells[index] = text_value.strip()
                matrix.append(cells)
            if not matrix or tuple(matrix[0]) != EXCEL_FIELDS:
                raise ImportContractError("Excel-kolommen wijken af van tabblad 'Alle artikelen'.")
            return [dict(zip(CSV_FIELDS, row)) for row in matrix[1:] if any(row)]
    except (BadZipFile, KeyError, ET.ParseError, IndexError, TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, ImportContractError):
            raise
        raise ImportContractError("Excelbestand kon niet veilig worden gelezen.") from exc


def read_proposals(data: bytes, filename: str):
    if not data or len(data) > MAX_BYTES:
        raise ImportContractError("Selecteer één bestand tot maximaal 5 MB.")
    filename = str(filename or "").lower()
    if filename.endswith(".csv"):
        rows = _csv_table(data)
    elif filename.endswith(".xlsx"):
        rows = _xlsx_table(data)
    else:
        raise ImportContractError("Alleen het Inhuis Excelbestand (.xlsx) of de bijbehorende CSV is toegestaan.")
    if not rows or len(rows) > MAX_ROWS:
        raise ImportContractError("Import bevat geen artikelen of meer dan 5.000 rijen.")
    ids = [row["product_id"] for row in rows]
    if any(not key or len(key) > 200 for key in ids) or len(set(ids)) != len(ids):
        raise ImportContractError("Dubbele of ontbrekende Catalogus-ID's; niets ingelezen.")
    if any(not re.fullmatch(r"[0-9a-f]{64}", row["snapshot_sha256"]) for row in rows):
        raise ImportContractError("Een of meer controlesleutels ontbreken of zijn ongeldig.")
    return rows


def current_products(conn):
    """Reuse the exact ID/name/classification snapshot exported by PR691."""
    archive_bytes = build_catalog_classification_export(conn)
    with ZipFile(io.BytesIO(archive_bytes)) as archive:
        reader = csv.DictReader(io.StringIO(archive.read("catalogus.csv").decode("utf-8-sig")), delimiter=";")
        return {row["product_id"]: row for row in reader}


def _official_gpc(conn, codes):
    if not codes:
        return {}
    rows = conn.execute(text("""
        SELECT p.gpc_brick_code AS code, p.gpc_brick_name AS name
        FROM gpc_product_groups p
        JOIN gpc_bricks b ON b.brick_code = p.gpc_brick_code
        WHERE p.language_code = 'nl' AND p.active = TRUE
          AND p.gpc_brick_code = ANY(:codes)
    """), {"codes": list(codes)}).mappings().all()
    return {str(row["code"]): str(row["name"] or "") for row in rows}


def _official_cbs(conn, codes):
    if not codes:
        return {}
    rows = conn.execute(text("""
        SELECT c.cbs_code AS code, c.name_nl AS name, c.reference_version,
               c.valid_from
        FROM cbs_ecoicop_categories c
        WHERE c.cbs_code = ANY(:codes)
          AND NOT EXISTS (
             SELECT 1 FROM cbs_ecoicop_categories child
             WHERE child.parent_code = c.cbs_code
               AND child.reference_version = c.reference_version
          )
        ORDER BY c.valid_from DESC, c.reference_version DESC
    """), {"codes": list(codes)}).mappings().all()
    result = {}
    for row in rows:
        code = str(row["code"])
        if code not in result:
            result[code] = {"name": str(row["name"] or ""),
                            "reference_version": str(row["reference_version"])}
    return result


def preview_import(conn, rows):
    actual = current_products(conn)
    gs_codes = {x.get(key) for x in rows for key in ("gpc_voorstel", "gpc_controlealternatief")} - {""}
    cb_codes = {x.get(key) for x in rows for key in ("cbs_voorstel", "cbs_controlealternatief")} - {""}
    gs_ref = _official_gpc(conn, gs_codes)
    cb_ref = _official_cbs(conn, cb_codes)
    out = []
    for x in rows:
        current = actual.get(x["product_id"])
        problem = ""
        if not current:
            problem = "Catalogusartikel ontbreekt of is verwijderd."
        elif current["name"] != x["name"] or current["snapshot_sha256"] != x["snapshot_sha256"]:
            problem = "Catalogusartikel of classificatie is sinds de export gewijzigd."
        elif (x["gpc_bestaand"] or "") != (current.get("gpc_brick_code") or "") or (
             x["cbs_bestaand"] or "") != (current.get("cbs_code") or ""):
            problem = "Bestaande classificaties verschillen van het exportbestand."
        gpc_options = [{"code": code, "label": gs_ref[code], "kind": kind}
                       for code, kind in ((x["gpc_voorstel"], "voorstel"),
                                          (x["gpc_controlealternatief"], "bestaand controleren"))
                       if code and code in gs_ref]
        cbs_options = [{"code": code, "label": cb_ref[code]["name"],
                        "reference_version": cb_ref[code]["reference_version"], "kind": kind}
                       for code, kind in ((x["cbs_voorstel"], "voorstel"),
                                          (x["cbs_controlealternatief"], "bestaand controleren"))
                       if code and code in cb_ref]
        out.append({
            "product_id": x["product_id"], "name": x["name"], "brand": x["brand"],
            "snapshot_sha256": x["snapshot_sha256"],
            "current_gpc": current.get("gpc_brick_code", "") if current else "",
            "current_cbs": current.get("cbs_code", "") if current else "",
            "gpc_status": x["gpc_status"], "cbs_status": x["cbs_status"],
            "gpc_reason": x["gpc_onderbouwing"], "cbs_reason": x["cbs_onderbouwing"],
            "review_existing": bool(x["controle_bestaande_code"]),
            "gpc_options": gpc_options, "cbs_options": cbs_options,
            "problem": problem,
            "invalid_gpc": [code for code in (x["gpc_voorstel"], x["gpc_controlealternatief"]) if code and code not in gs_ref],
            "invalid_cbs": [code for code in (x["cbs_voorstel"], x["cbs_controlealternatief"]) if code and code not in cb_ref],
        })
    return {
        "rows": out,
        "total": len(out),
        "review_existing": sum(bool(x["review_existing"]) for x in out),
        "blocked": sum(bool(x["problem"] or x["invalid_gpc"] or x["invalid_cbs"]) for x in out),
        "no_changes_yet": True,
    }


def confirm_import(conn, decisions, *, actor_id: str):
    if not actor_id or not (1 <= len(decisions) <= 100):
        raise ImportContractError("Kies 1 tot en met 100 classificaties per verwerking.")
    keys = [(d["product_id"], d["system"]) for d in decisions]
    if len(set(keys)) != len(keys):
        raise ImportContractError("Dubbele classificatiekeuzes zijn niet toegestaan.")
    if any(d.get("approved") is not True or d["system"] not in ("gpc", "cbs")
           for d in decisions):
        raise ImportContractError("Elke gekozen classificatie moet expliciet zijn goedgekeurd.")
    # Product locks and a single database transaction prevent a partial import.
    for pid in sorted({d["product_id"] for d in decisions}):
        if not conn.execute(text("SELECT id FROM global_products WHERE id = :id AND status <> 'deleted' FOR UPDATE"), {"id": pid}).first():
            raise ImportContractError("Catalogusartikel ontbreekt; niets verwerkt.")
    live = current_products(conn)
    gs_ref = _official_gpc(conn, {d["code"] for d in decisions if d["system"] == "gpc"})
    cb_ref = _official_cbs(conn, {d["code"] for d in decisions if d["system"] == "cbs"})
    gs_updates, cb_decisions, unchanged = [], [], 0
    for d in decisions:
        row = live.get(d["product_id"])
        if not row or row["name"] != d["expected_name"]:
            raise ImportContractError("Catalogusartikel bestaat niet meer of heeft een andere naam.")
        if not re.fullmatch("[0-9a-f]{64}", str(d["expected_sha256"])) or row["snapshot_sha256"] != d["expected_sha256"]:
            raise ImportContractError("Het importbestand is verouderd. Exporteer opnieuw en controleer de voorstellen.")
        if d["system"] == "gpc":
            if d["code"] not in gs_ref:
                raise ImportContractError("GS1-code is geen actieve officiële GPC Brick.")
            current = row.get("gpc_brick_code") or ""
        else:
            if d["code"] not in cb_ref or cb_ref[d["code"]]["reference_version"] != d["reference_version"]:
                raise ImportContractError("CBS-code is niet de officiële eindcategorie van deze versie.")
            current = row.get("cbs_code") or ""
        if current == d["code"]:
            unchanged += 1
            continue
        if current and not d.get("allow_replace"):
            raise ImportContractError("Bestaande classificatie mag alleen na afzonderlijke vervangingsgoedkeuring worden gewijzigd.")
        if d["system"] == "gpc":
            gs_updates.append(d)
        else:
            prior = conn.execute(text("""
                SELECT version, is_active FROM global_product_cbs_classifications
                WHERE global_product_id = :id FOR UPDATE
            """), {"id": d["product_id"]}).mappings().first()
            cb_decisions.append({
                "global_product_id": d["product_id"], "expected_product_name": d["expected_name"],
                "cbs_code": d["code"], "reference_version": d["reference_version"],
                "expected_version": int(prior["version"]) if prior else 0,
            })
    # All writes are in the caller's transaction; CBS service writes audit history.
    for d in gs_updates:
        conn.execute(text("""
            INSERT INTO global_product_gpc_bricks
                (global_product_id, brick_code, assignment_source, confidence, updated_at)
            VALUES (:id, :code, 'explicit_classification_import', 1.0, CURRENT_TIMESTAMP)
            ON CONFLICT (global_product_id) DO UPDATE SET
                brick_code = excluded.brick_code,
                assignment_source = excluded.assignment_source,
                confidence = excluded.confidence,
                updated_at = CURRENT_TIMESTAMP
        """), {"id": d["product_id"], "code": d["code"]})
    if cb_decisions:
        confirm_cbs_batch(conn, cb_decisions, actor_id=actor_id)
    return {"updated_gpc": len(gs_updates), "updated_cbs": len(cb_decisions),
            "unchanged": unchanged, "processed": len(decisions)}
