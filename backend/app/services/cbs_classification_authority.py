"""Strict, non-mutating CBS ECOICOPv2 reference validation.

An old taxonomic proof is not a writable CBS authority. Importers must supply
verified parent relationships and source metadata; no prefix heuristic or
Shopify/GS1 crosswalk is allowed.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

_CBS_CODE = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_LEVEL = 5


def validate_cbs_code(value: object) -> str:
    """Accept exactly six ASCII decimal digits as a string, retaining zeros."""
    if not isinstance(value, str) or _CBS_CODE.fullmatch(value) is None:
        raise ValueError("CBS-code moet tekst zijn met precies zes cijfers.")
    return value


def validate_cbs_reference(rows: Iterable[Mapping[str, object]], *, reference_version: str,
                           source_sha256: str) -> list[dict[str, object]]:
    """Validate a *verified* complete hierarchy, without database side effects.

    Never infer a parent from a numeric prefix: ECOICOPv2 structure must come
    from an independently checked official CBS source.
    """
    if not isinstance(reference_version, str) or not reference_version.strip():
        raise ValueError("CBS-bronversie ontbreekt.")
    if not isinstance(source_sha256, str) or _SHA256.fullmatch(source_sha256) is None:
        raise ValueError("De bronchecksum moet een SHA-256 in hexadecimale vorm zijn.")

    prepared: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("CBS-categorie is geen geldig gegevensobject.")
        code = validate_cbs_code(row.get("cbs_code"))
        name = row.get("name_nl")
        level = row.get("level")
        parent = row.get("parent_code")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"CBS-categorie {code} mist een Nederlandse naam.")
        if type(level) is not int or not (1 <= level <= _MAX_LEVEL):
            raise ValueError(f"CBS-categorie {code} heeft geen geldig niveau.")
        if parent is not None:
            validate_cbs_code(parent)
            if parent == code:
                raise ValueError(f"CBS-categorie {code} verwijst naar zichzelf.")
        if code in prepared:
            raise ValueError(f"Dubbele CBS-code: {code}.")
        prepared[code] = {
            "cbs_code": code,
            "name_nl": name.strip(),
            "level": level,
            "parent_code": parent,
            "reference_version": reference_version.strip(),
            "source_sha256": source_sha256,
        }

    if not prepared:
        raise ValueError("Een lege CBS-referentie mag niet gepubliceerd worden.")

    for code, row in prepared.items():
        parent = row["parent_code"]
        if parent is None:
            if row["level"] != 1:
                raise ValueError(f"CBS-categorie {code} mist een officiële ouder.")
        else:
            ancestor = prepared.get(parent)
            if ancestor is None:
                raise ValueError(f"CBS-categorie {code} verwijst naar ontbrekende ouder {parent}.")
            if row["level"] != ancestor["level"] + 1:
                raise ValueError(f"CBS-categorie {code} heeft een onjuist niveau ten opzichte van {parent}.")

    return list(prepared.values())
