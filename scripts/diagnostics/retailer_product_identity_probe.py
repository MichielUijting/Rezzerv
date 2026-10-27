"""Read-only source identity audit; never imported by application startup.

This is the first retailer-product proof, not a catalog importer. It separates
explicit GTIN evidence, ambiguous scanner codes and retailer SKU namespaces.
No account login, network call, name-based product identity or database write.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import secrets


PROVIDERS = ("ah", "jumbo", "lidl", "picnic", "aldi")
EXPLICIT_GTIN_KEYS = ("gtin", "ean", "barcode")
SCANNER_KEYS = ("codeInput", "productCode")
SKU_KEYS = ("retailer_sku", "retailerSku", "sku", "articleNumber", "articleId")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_RECEIPTS = 2000
MAX_LINES = 2000


class SourceReadError(ValueError):
    """Fixed diagnostic code only, never an exception containing private data."""


def valid_gtin(value):
    """Exact ASCII digits, valid length/check digit; no digit stripping/padding."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:[0-9]{8}|[0-9]{12,14})", value):
        return False
    if set(value) == {"0"}:
        return False
    total = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(value[:-1])))
    return (10 - total % 10) % 10 == int(value[-1])


def code_value(value):
    # JSON numbers have already lost possible leading zeroes: do not reconstruct.
    return value.strip() if isinstance(value, str) and len(value) <= 180 else ""


def line_evidence(provider, item):
    """Return allowlisted identifiers only. Never expose arbitrary source keys."""
    if provider not in PROVIDERS or not isinstance(item, dict):
        raise ValueError("Unsupported source")
    nested = next((item[k] for k in ("product", "article", "item") if isinstance(item.get(k), dict)), {})
    explicit = []
    ambiguous = []
    skus = []
    numeric_fields = 0
    for prefix, obj in (("line", item), ("product", nested)):
        for key in EXPLICIT_GTIN_KEYS + SCANNER_KEYS:
            if key not in obj or obj[key] in (None, ""):
                continue
            value = code_value(obj[key])
            numeric_fields += int(isinstance(obj[key], (int, float)) and not isinstance(obj[key], bool))
            entry = {"field": prefix + "." + key, "value": value,
                     "check_digit_valid": valid_gtin(value)}
            (explicit if key in EXPLICIT_GTIN_KEYS else ambiguous).append(entry)
        for key in SKU_KEYS + (("id",) if prefix == "product" or provider in {"ah", "picnic"} else ()):
            value = code_value(obj.get(key))
            # Retailer IDs can be JSON integers (AH uses these). Preserve the
            # source namespace; this conversion never produces a GTIN.
            if isinstance(obj.get(key), int) and not isinstance(obj[key], bool) and 0 <= obj[key] < 10**30:
                value = str(obj[key])
            if value:
                skus.append({"field": prefix + "." + key, "value": value})
    gtins = {e["value"] for e in explicit if e["check_digit_valid"]}
    invalid_explicit = any(not e["check_digit_valid"] for e in explicit)
    # Different string lengths can be legitimate GTIN zero-padding aliases.
    # Preserve observations, but never choose between conflicting identities.
    normalized = {v.zfill(14) for v in gtins}
    conflict = len(normalized) > 1
    status = ("conflicting_gtins" if conflict else "invalid_explicit_gtin" if invalid_explicit
              else "explicit_gtin_observed" if gtins else "scanner_code_needs_confirmation" if ambiguous
              else "retailer_sku_only" if skus else "no_identifier")
    return {"provider": provider, "status": status, "explicit_gtins": explicit,
            "scanner_codes": ambiguous, "retailer_skus": skus,
            "numeric_identifier_fields": numeric_fields,
            "retailer_product_verified": False, "barcode_link_verified": False}


def source_lines(envelope):
    """Read only the bounded, known retailer-envelope layout we actually store."""
    if not isinstance(envelope, dict) or envelope.get("schema_version") != "1.0":
        raise SourceReadError("unknown_envelope_version")
    provider = envelope.get("provider")
    if provider not in PROVIDERS:
        raise SourceReadError("unknown_provider")
    root = envelope.get("receipt")
    if not isinstance(root, dict):
        raise SourceReadError("missing_receipt_object")
    original_root = root
    for wrapper in ("receipt", "data", "ticket", "order"):
        if isinstance(root.get(wrapper), dict):
            root = root[wrapper]
    lines = next((candidate[k] for candidate in (original_root, root)
                  for k in ("items", "products", "lines", "entries", "receiptLines", "basketItems")
                  if isinstance(candidate.get(k), list)), None)
    if lines is None or len(lines) > MAX_LINES or any(not isinstance(x, dict) for x in lines):
        raise SourceReadError("unknown_or_excessive_line_layout")
    return provider, lines


def read_envelope(path, root, expected_hash):
    """Constrain path, size and content hash before opening private source data."""
    try:
        source = Path(path).resolve()
        try:
            source.relative_to(Path(root).resolve())
        except ValueError:
            raise SourceReadError("outside_storage_root") from None
        if not source.is_file():
            raise SourceReadError("source_file_missing")
        if source.stat().st_size > MAX_FILE_BYTES:
            raise SourceReadError("source_file_too_large")
        with source.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise SourceReadError("source_file_too_large")
        if hashlib.sha256(data).hexdigest() != expected_hash:
            raise SourceReadError("source_hash_mismatch")
        try:
            return json.loads(data)
        except (ValueError, UnicodeError):
            raise SourceReadError("source_json_invalid") from None
    except OSError:
        raise SourceReadError("source_file_unreadable") from None


def audit(conn, storage_root):
    """Requires an already read-only PostgreSQL snapshot. All output is aggregate.

    No names, IDs, codes, prices, source paths, account details or raw JSON leave
    the source reader. Household references are salted for this execution only.
    """
    from sqlalchemy import text
    if conn.dialect.name != "postgresql" or conn.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
        raise ValueError("Read-only PostgreSQL transaction required")
    rows = conn.execute(text("""
        SELECT rr.id, rr.household_id, rr.storage_path, rr.sha256_hash,
               rs.source_path AS provider
        FROM raw_receipts rr
        JOIN receipt_sources rs ON rs.id=rr.source_id AND rs.household_id=rr.household_id
        WHERE rs.type='retailer_api'
          AND rs.source_path IN ('ah','jumbo','lidl','picnic','aldi')
          AND rr.mime_type='application/vnd.inhuis.retailer-receipt+json'
        ORDER BY rr.household_id, rs.source_path, rr.id
        LIMIT :limit
    """), {"limit": MAX_RECEIPTS + 1}).mappings().all()
    if len(rows) > MAX_RECEIPTS:
        raise ValueError("More than 2000 source receipts; narrow audit required")
    salt = secrets.token_bytes(32)
    groups = {}
    for row in rows:
        household = hashlib.sha256(salt + str(row["household_id"]).encode()).hexdigest()[:12]
        key = household, row["provider"]
        group = groups.setdefault(key, {"household_ref": household, "provider": row["provider"],
            "source_receipts": 0, "source_errors": 0, "source_error_reasons": Counter(), "source_lines": 0,
            "explicit_nonproduct_lines_skipped": 0, "statuses": Counter(), "numeric_identifier_fields": 0,
            "persisted_product_lines": 0, "persisted_valid_gtin_shape": 0,
            "persisted_sku_present": 0, "barcode_also_sku": 0})
        group["source_receipts"] += 1
        # Saved identifiers are independent evidence: count them even when the
        # original source file is absent, inaccessible or fails integrity checks.
        saved = conn.execute(text("""
            SELECT rtl.barcode, rtl.external_article_code
            FROM receipt_table_lines rtl JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
            WHERE rt.raw_receipt_id=:raw_id AND rt.household_id=:household
              AND rtl.line_role='product' AND rtl.inventory_eligible=1
              AND COALESCE(rtl.is_deleted,FALSE)=FALSE
        """), {"raw_id": row["id"], "household": row["household_id"]}).mappings().all()
        for item in saved:
            barcode = code_value(item["barcode"])
            sku = code_value(item["external_article_code"])
            group["persisted_product_lines"] += 1
            group["persisted_valid_gtin_shape"] += int(valid_gtin(barcode))
            group["persisted_sku_present"] += int(bool(sku))
            group["barcode_also_sku"] += int(bool(sku) and sku == barcode)
        try:
            provider, lines = source_lines(read_envelope(row["storage_path"], storage_root, row["sha256_hash"]))
            if provider != row["provider"]:
                raise SourceReadError("provider_mismatch")
        except SourceReadError as exc:
            group["source_errors"] += 1
            group["source_error_reasons"][str(exc)] += 1
            continue
        except (ValueError, OSError, TypeError, UnicodeError):
            group["source_errors"] += 1
            group["source_error_reasons"]["other_source_structure_error"] += 1
            continue
        for item in lines:
            role = next((item[k] for k in ("line_type", "lineType", "type") if item.get(k)), "product")
            if role not in {"product", "article", "item"}:
                group["explicit_nonproduct_lines_skipped"] += 1
                continue
            observation = line_evidence(provider, item)
            group["source_lines"] += 1
            group["statuses"][observation["status"]] += 1
            group["numeric_identifier_fields"] += observation["numeric_identifier_fields"]
        # Aggregate separately: raw rows may be folded during import (weights),
        # so there is deliberately NO positional/name-based raw-to-saved join.
    return {"schema_version": "1.0", "probe_version": 2, "read_only": True, "network_requests": 0,
        "retailer_product_verified": False, "barcode_link_verified": False,
        "scope": "Stored retailer API source envelopes, including historical receipts; no new fetch/import",
        "groups": list(groups.values()),
        "providers_without_sources": [p for p in PROVIDERS if not any(g["provider"] == p for g in groups.values())],
        "interpretation": "A valid check digit proves code structure only, never product identity. Source and saved counts have different denominators. No automatic links."}


def main():
    # No app.db/main imports: never trigger schema preflight, startup or writes.
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = make_url(os.environ.get("DATABASE_URL") or "")
    if url.get_backend_name() != "postgresql" or url.host != "postgres" or (url.port or 5432) != 5432:
        raise ValueError("Expected existing Compose PostgreSQL route")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url, connect_args={"connect_timeout": 8}, isolation_level="REPEATABLE READ")
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql("SET LOCAL statement_timeout='25s'")
            conn.exec_driver_sql("SET LOCAL lock_timeout='3s'")
            result = audit(conn, Path(os.environ.get("RECEIPT_STORAGE_ROOT", "/app/data/receipts/raw")))
        print(json.dumps(result, ensure_ascii=True))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Driver/file/JSON exceptions can contain credentials or raw source data.
        print('VEILIG GESTOPT: broncontrole niet voltooid; geen gegevens gewijzigd.')
        raise SystemExit(1) from None
