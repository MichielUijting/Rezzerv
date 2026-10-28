"""Offline regression for the read-only taxonomy proof 4. No DB or network."""

import ast
import json
from pathlib import Path

from tools.inhuis_taxonomy_proof4_core import (
    build_brick_term_index,
    build_gpc_classes,
    build_seed_index,
    class_hypothesis,
    combined_direction,
    existing_code_warnings,
    group_direction,
    norm,
)


root = Path(__file__).resolve().parent.parent
runner = (root / "tools" / "inhuis_taxonomy_proof4.py").read_text(encoding="utf-8")
ast.parse(runner)
assert 'SET TRANSACTION READ ONLY' in runner
assert 'conn.rollback()' in runner
assert 'pgm.active = 1 AND pig.active = 1' in runner
assert 'list_all_external_articles(conn=conn)' in runner
assert 'lookup_off_product' not in runner

seed = json.loads((root / "backend/app/data/product_taxonomy_seed.json").read_text(encoding="utf-8"))
ref = json.loads((root / "backend/app/data/gpc_bricks_nl.json").read_text(encoding="utf-8"))
official = {row["gpc_brick_code"]: row for row in ref["bricks"]}
index = build_seed_index(seed)
classes = build_gpc_classes(ref)
brick_terms = build_brick_term_index(ref)

def direction(name, retailer=""):
    return group_direction(name, retailer, index)


assert norm("Crème fraîche") == "creme fraiche"
assert direction("AH HV MELK", "ah")["group"] == "Zuivel"
assert "Winkelafkorting" in direction("AH HV MELK", "ah")["evidence"]
assert "Winkelafkorting" not in direction("AH HV MELK", "jumbo")["evidence"]
assert direction("T AH M GEHAKT", "albert heijn")["group"] == "Vlees"
assert direction("CR ME FRACHE 30", "lidl")["group"] == "Zuivel"
assert direction("KIKKERWTEN", "plus")["group"] == "Peulvrucht"
assert direction("Verse halfvolle melk", "lidl")["group"] == "Zuivel"
assert direction("Gouda belegen gerasp", "lidl")["group"] == "Zuivel"
assert direction("Jumbo Stroopwafels", "jumbo")["group"] == "Snack"
assert direction("PO-testartikel", "jumbo")["group"] == ""
assert direction("PLUSpunten", "plus")["group"] == ""
assert direction("Tuna", "lidl")["group"] == ""
assert direction("Gerasp", "unknown")["group"] == ""
assert combined_direction("Bloemkool", "lidl", index, brick_terms)["group"] == "Groente"
assert combined_direction("Basilicum", "lidl", index, brick_terms)["group"] == "Kruiden/smaakmakers"
assert combined_direction("Basilicum potplant", "lidl", index, brick_terms)["group"] == ""
assert combined_direction("Bio rozemarijn in pot", "lidl", index, brick_terms)["group"] == ""
assert combined_direction("JUMBO CROUT KNOFLOOK", "jumbo", index, brick_terms)["group"] == ""
assert combined_direction("Margarine bladerdeeg", "lidl", index, brick_terms)["group"] == ""
assert combined_direction("Kaneel", "lidl", index, brick_terms)["group"] == ""

# The existing GPC reference is not assumed correct simply because codes exist.
cases = (
    ("Kipgrillworst", "Vleeswaren", "10002888"),
    ("Kerrie", "", "10006371"),
    ("Rosmarijn Gebroken", "", "10006613"),
    ("Verstegen Venkelzaad", "", "10000459"),
    ("AARDAPPELSCHIJFJE SPEK-UI", "Groente", "10006835"),
    ("Krokante ontbijt granen", "Ontbijt", "10000288"),
    ("Zoete Aardappel Frites", "Groente", "10006111"),
)
for product, group, code in cases:
    assert existing_code_warnings(product, {"group": group}, official[code]), product

assert not existing_code_warnings("Broccoli", {"group": "Groente"}, official["10005988"])
proposal = class_hypothesis("Halfvolle melk", "Zuivel", classes)
assert not proposal or " > " in proposal  # At most a class-level suggestion.

print("TAXONOMIEPROEF 4 - OFFLINE SELFTEST GESLAAGD")
print("Geen database, Docker, netwerk, AI of betaalde dienst aangeroepen.")
