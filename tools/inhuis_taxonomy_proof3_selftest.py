"""Isolated read-only checks for taxonomy proof 3, no backend/DB startup."""

import ast
import collections
import json
import re
import unicodedata
from pathlib import Path


root = Path(__file__).resolve().parent.parent
source = (root / "tools" / "inhuis_taxonomy_proof3.py").read_text(encoding="utf-8")
tree = ast.parse(source)
assert "SET TRANSACTION READ ONLY" in source
assert "max_off_requests = 6" in source
assert "time.sleep(6)" in source

allowed_functions = {
    "norm", "safe", "compatible_with_category", "semantic_signature",
    "composite_head", "quality_flags", "off_direction",
}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in allowed_functions]
assert len(functions) == len(allowed_functions)
environment = {
    "collections": collections,
    "re": re,
    "unicodedata": unicodedata,
    "food_categories": {"groente", "zuivel", "vleeswaren", "snack", "fruit"},
    "category_family_hints": {"zuivel": ("melk", "yoghurt", "kaas")},
}
exec(compile(ast.Module(body=functions, type_ignores=[]), "taxonomy_helpers", "exec"), environment)

reference = json.loads((root / "backend" / "app" / "data" / "gpc_bricks_nl.json")
                       .read_text(encoding="utf-8"))
official = {row["gpc_brick_code"]: row for row in reference["bricks"]}
quality = environment["quality_flags"]
head = environment["composite_head"]

assert head("Croissant ham/kaas") == "croissant"
assert head("Verse pasta champignons") == "pasta"
assert head("Maggi ovenschotel prei") == "ovenschotel"
assert head("Magere yoghurt") == ""
assert quality("Kipgrillworst", "Vleeswaren", official["10002888"])
assert quality("Kerrie", "", official["10006371"])
assert quality("Verstegen Venkelzaad", "", official["10000459"])
assert quality("Rosmarijn Gebroken", "", official["10006613"])
assert not quality("Chocopops", "Broodbeleg", official["10000284"])
assert quality("BIO RODE BIET VACUM", "Groente", official["10006144"])
assert environment["off_direction"](["en:cheeses"]) == "Zuivel / kaas"
assert environment["off_direction"](["en:cheeses", "en:fruits"]) == "Meerdere mogelijke OFF-richtingen"

print("TAXONOMIEPROEF 3 - OFFLINE SELFTEST GESLAAGD")
print("Geen database, Docker, OFF of applicatie gestart.")
