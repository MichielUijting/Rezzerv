"""Read-only GS1 taxonomy evidence proof 3 for Inhuis.

Run only in the existing backend via the repository tools read-only mount.
This is analysis only: no database mutations or automatic GS1 assignments.
"""

import collections
import datetime
import json
import os
import re
import sys
import traceback
import unicodedata
from pathlib import Path


def _safe_unhandled_error(error_type, error, traceback_object):
    """Prevent accidental disclosure of passwords/DSNs in PO report files."""
    details = "".join(traceback.format_exception(error_type, error, traceback_object))
    details = re.sub(
        r"(?i)postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+",
        "[DATABASEVERBINDING AFGESCHERMD]",
        details,
    )
    details = re.sub(
        r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)[^\s,'\"]+",
        r"\1\2[AFGESCHERMD]",
        details,
    )
    print("INHUIS - TAXONOMIEPROEF 3 - VEILIG GESTOPT", file=sys.stderr)
    print("Geen gegevens gewijzigd; technische diagnose:", file=sys.stderr)
    print("\n".join(details.splitlines()[-35:]), file=sys.stderr)


sys.excepthook = _safe_unhandled_error

from sqlalchemy import text
from app.db import DATASTORE_KIND, engine
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.gtin_validation_service import is_valid_gtin


def safe(value, limit=110):
    value = " ".join(str(value or "").split())
    value = value.replace("|", "/").replace(";", ",")
    return value[:limit]


def norm(value):
    folded = unicodedata.normalize("NFKD", str(value or "").casefold())
    letters = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", letters))


if DATASTORE_KIND != "postgresql":
    raise RuntimeError("VEILIG GESTOPT: de bestaande runtime is geen PostgreSQL")

app_data_path = Path(__import__("app").__file__).resolve().parent / "data"
gpc_path = app_data_path / "gpc_bricks_nl.json"
if not gpc_path.is_file():
    raise RuntimeError("VEILIG GESTOPT: de Nederlandse GS1-referentie ontbreekt in de actieve backend")
reference = json.loads(gpc_path.read_text(encoding="utf-8"))
bricks = reference.get("bricks") or []
if len(bricks) < 5000:
    raise RuntimeError("VEILIG GESTOPT: de GS1-referentie is onverwacht onvolledig")

gpc_by_code = {}
rank_rows = []
for row in bricks:
    code = str(row.get("gpc_brick_code") or "")
    if not re.fullmatch(r"\d{8}", code):
        continue
    gpc_by_code[code] = row
    rank_rows.append({
        "brick_code": code,
        "brick_description": row.get("gpc_brick_name") or "",
        "class_code": row.get("gpc_class_code") or "",
        "class_description": row.get("gpc_class_name") or "",
        "family_code": row.get("gpc_family_code") or "",
        "family_description": row.get("gpc_family_name") or "",
        "segment_code": row.get("gpc_segment_code") or "",
        "segment_description": row.get("gpc_segment_name") or "",
        "reference_source": "gs1_gpc_nl",
    })

# Een omgekeerde index kiest snel relevante OFFICIELE GS1-rijen. Er wordt
# geen eigen vervangende producttaxonomie aangemaakt of geschreven.
ignored = {
    "van", "voor", "het", "met", "zonder", "diepvries", "houdbaar",
    "onbewerkt", "onverwerkt", "bereid", "bewerkt", "levensmiddelen",
    "dranken", "andere", "producten", "product", "beperkt", "niet",
}
index = collections.defaultdict(set)
for i, row in enumerate(rank_rows):
    categories = " ".join(str(row[field] or "") for field in (
        "brick_description", "class_description", "family_description"
    ))
    for token in set(norm(categories).split()):
        if len(token) >= 4 and token not in ignored:
            index[token[:5]].add(i)

# Bestaande lokale synoniemen mogen als zoekhulp dienen, maar nooit als
# zelfstandig bewijs voor een officiële GS1-code. Geen seeding of andere writes.
seed_path = app_data_path / "product_taxonomy_seed.json"
synonyms = []
seed_verified = {}
if seed_path.is_file():
    for item in json.loads(seed_path.read_text(encoding="utf-8")).get("taxonomy") or []:
        description = " ".join(str(item.get(key) or "") for key in (
            "canonical_name", "category", "product_type"
        ))
        category = str(item.get("category") or "")
        for verified_name, verified_code in (item.get("verified_official_gpc_by_exact_name") or {}).items():
            if str(verified_code) in gpc_by_code:
                seed_verified[norm(verified_name)] = str(verified_code)
        for name in [item.get("canonical_name"), *(item.get("synonyms") or [])]:
            value = norm(name)
            if len(value) >= 4:
                synonyms.append((value, description, category))
    synonyms.sort(key=lambda value: -len(value[0]))

# De lokale producttermen zijn alleen herkenningshulp. Ze geven GEEN recht
# om een officiële GS1 Brick vast te leggen. Het bekende domein bepaalt
# hoogstens welke officiële GS1-hoofdgroep als kandidaat mag meedoen.
food_categories = {
    "groente", "zuivel", "drank", "fruit", "bakkerij", "vleeswaren",
    "snack", "graan", "saus", "soep", "maaltijd", "vlees", "broodbeleg",
    "peulvrucht", "ontbijt", "babyvoeding", "eieren", "kruiden", "pasta",
}
category_family_hints = {
    "zuivel": ("melk", "yoghurt", "kaas", "boter", "room", "eieren"),
    "groente": ("groenten", "bladgroenten", "wortel", "knolgewassen"),
    "fruit": ("fruit",),
    "vleeswaren": ("vlees", "worsten", "gevogelte"),
    "vlees": ("vlees", "worsten", "gevogelte"),
    "drank": ("dranken", "sap", "thee", "koffie", "wijn", "bier", "water"),
    "pasta": ("pasta", "graanproducten"),
    "kruiden": ("kruiden", "specerijen", "extracten"),
    "bakkerij": ("bakkerij", "brood", "graanproducten"),
    "broodbeleg": ("smeerbeleg", "zoetwaren", "spreads"),
}


def seed_context(name):
    key = norm(name)
    words = key.split()
    for term, description, category in synonyms:
        if (" " + term + " " in " " + key + " " or
                (len(term) >= 5 and any(word.endswith(term) for word in words))):
            return category, description
    return "", ""


def compatible_with_category(category, official_row):
    category_key = norm(category)
    if category_key in food_categories and str(official_row.get("gpc_segment_code") or "") != "50000000":
        return False
    hints = category_family_hints.get(category_key)
    if hints:
        hierarchy_text = norm(" ".join(str(official_row.get(field) or "") for field in (
            "gpc_family_name", "gpc_class_name"
        )))
        return any(hint in hierarchy_text for hint in hints)
    return True

with engine.connect() as conn:
    # Fail-closed: PostgreSQL zelf weigert iedere INSERT/UPDATE/DELETE in deze transactie.
    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    products = [dict(row) for row in conn.execute(text(
        "SELECT id, name, brand, primary_gtin FROM global_products ORDER BY name, id"
    )).mappings().all()]
    memberships = conn.execute(text("""
        SELECT pgm.global_product_id, pig.gpc_brick_code AS brick_code
        FROM product_group_memberships pgm
        JOIN product_inventory_groups pig
          ON pig.inventory_group_key = pgm.inventory_group_key
        WHERE pgm.active = 1 AND pig.active = 1
          AND pig.gpc_brick_code IS NOT NULL
    """)).mappings().all()
    assignments = conn.execute(text(
        "SELECT global_product_id, brick_code FROM global_product_gpc_bricks"
    )).mappings().all()
    # Dit is dezelfde bestaande, alleen-lezen bronselectie als in ED2.
    overview = list_all_external_articles(conn=conn)
    conn.rollback()

product_gpc = collections.defaultdict(set)
for row in list(memberships) + list(assignments):
    code = str(row.get("brick_code") or "")
    if code in gpc_by_code:
        product_gpc[str(row.get("global_product_id") or "")].add(code)

gtin_products = collections.defaultdict(set)
for product in products:
    gtin = str(product.get("primary_gtin") or "").strip()
    if gtin:
        gtin_products[gtin].add(str(product.get("id") or ""))

cached = {}


def suggestion(name, category=""):
    normalized_name = norm(name)
    if not normalized_name:
        return None
    key = (normalized_name, norm(category))
    if key in cached:
        return cached[key]
    extra = ""
    for term, description, unused_category in synonyms:
        if " " + term + " " in " " + normalized_name + " ":
            extra = norm(description)
            break
    token_weight = collections.Counter()
    for source_text, source_weight in ((normalized_name, 1.0), (extra, 0.55)):
        for token in set(source_text.split()):
            stem = token[:5]
            if len(token) >= 4 and stem in index and token not in ignored:
                # Een onderscheidende term weegt zwaarder dan een zeer brede term.
                token_weight[stem] += source_weight / (1.0 + len(index[stem]) / 70.0)
    preselect = collections.Counter()
    for token, weight in token_weight.most_common(16):
        for item_id in index[token]:
            if norm(category) in food_categories and rank_rows[item_id]["segment_code"] != "50000000":
                continue
            preselect[item_id] += weight
    if not preselect:
        cached[key] = None
        return None
    original_stems = {token[:5] for token in normalized_name.split() if len(token) >= 4}
    extra_stems = {token[:5] for token in extra.split() if len(token) >= 4}
    ranked = []
    for item_id, preliminary in preselect.most_common(100):
        candidate = rank_rows[item_id]
        score = 0.0
        for field, weight in (
            ("brick_description", 2.0),
            ("class_description", 1.1),
            ("family_description", 0.7),
        ):
            stems = {token[:5] for token in norm(candidate[field]).split() if len(token) >= 4}
            score += weight * len(stems & original_stems)
            score += 0.35 * weight * len(stems & extra_stems)
        if score >= 1.4:
            ranked.append((score + preliminary / 10.0, candidate))
    ranked.sort(key=lambda value: (-value[0], value[1]["brick_code"]))
    cached[key] = {
        **ranked[0][1],
        "proposal_score": round(ranked[0][0], 2),
        "ambiguous": bool(len(ranked) > 1 and ranked[1][0] >= ranked[0][0] * 0.90),
    } if ranked else None
    return cached[key]


def hierarchy(gpc_code):
    row = gpc_by_code.get(gpc_code) or {}
    return " > ".join(safe(row.get(field), 70) for field in (
        "gpc_segment_name", "gpc_family_name", "gpc_class_name", "gpc_brick_name"
    ) if row.get(field))


def class_hierarchy(row):
    return " > ".join(safe(row.get(field), 70) for field in (
        "gpc_segment_name", "gpc_family_name", "gpc_class_name"
    ) if row.get(field))


def semantic_signature(name):
    """Hoogstens een kwaliteitswaarschuwing; nooit bron voor een Brick."""
    key = " " + norm(name) + " "
    rules = (
        (("kerrie", "venkelzaad", "rozemarijn", "rosmarijn", "rosemary", "cayennepeper", "uienpoeder"),
         ("kruiden", "specerijen", "extracten"), "Kruiden/specerijen"),
        (("chocopops", "choco shells", "ontbijtgranen", "muesli"),
         ("graan", "ontbijt"), "Ontbijtgranen"),
        (("pepita", "amandelen", "hazelnoten", "pistache"),
         ("noten", "zaad"), "Noten/zaad"),
        (("chorizo", "grillworst", "rookworst", "salami"),
         ("vlees", "worst", "gevogelte"), "Vleeswaren"),
        (("eieren", " ei "),
         ("eieren", "eiproduct"), "Eieren"),
    )
    for terms, family_clues, label in rules:
        if any(" " + norm(term) + " " in key or any(
                word.startswith(norm(term)) and len(norm(term)) >= 5
                for word in key.split()) for term in terms):
            return family_clues, label
    return (), ""


def composite_head(name):
    """Een ingrediënt zegt niets over de GS1-klasse van het hele product."""
    value = norm(name)
    words = set(value.split())
    heads = {
        "croissant", "ovenschotel", "pasta", "lasagne", "pizza",
        "crackers", "sandwich", "wrap", "wraps", "tosti", "stokbrood",
        "soep", "kerriesoep", "kroepoek", "kroe", "nasi", "bami",
        "salade", "curry", "risotto", "quiche",
    }
    ingredients = {
        "kaas", "ham", "kip", "prei", "champignons", "champignon",
        "tomaat", "tomaten", "biet", "groenten", "wortel", "cassave",
        "ui", "uien", "spek", "melk", "broccoli", "courgette",
    }
    head = sorted(heads & words)
    if not head and any(word.endswith("soep") and word != "soep" for word in words):
        head = ["soep"]
    if head and words & ingredients:
        return head[0]
    return ""


def quality_flags(name, category, official):
    """Conservatieve contradictietest voor bestaande en voorgestelde codes."""
    key = norm(name)
    hierarchy_text = norm(" ".join(str(official.get(field) or "") for field in (
        "gpc_segment_name", "gpc_family_name", "gpc_class_name", "gpc_brick_name"
    )))
    flags = []
    signature_words, signature_label = semantic_signature(name)
    known_food = norm(category) in food_categories or bool(signature_words)
    if known_food and str(official.get("gpc_segment_code") or "") != "50000000":
        flags.append("Levensmiddel lijkt buiten het GS1-voedselsegment ingedeeld")
    if signature_words and not any(term in hierarchy_text for term in signature_words):
        flags.append("Herkenbaar hoofdproduct " + signature_label + " past niet bij GS1-hierarchie")

    head = composite_head(name)
    if head:
        if any(token in hierarchy_text for token in (
            "onbewerkt", "onverwerkt", "vers", "verse kruiden",
        )):
            flags.append("Samengesteld product (" + head + ") mag geen verse ingrediëntklasse krijgen")
        elif head in {"croissant", "crackers", "pasta", "ovenschotel", "soep", "kerriesoep"}:
            family = norm(official.get("gpc_family_name") or "")
            if any(term in family for term in ("kaas", "groenten", "stengelgroenten")):
                flags.append("Samengesteld product (" + head + ") verward met ingrediënt")

    # Deze bewoordingen sluiten uit dat een bewerkt/verpakt product op basis
    # van een losse grondstofnaam als 'onbewerkt/vers' wordt geclassificeerd.
    processed_terms = ("gezeefd", "zongedroogd", "gedroogde", "vacum", "vacuum", "puree")
    if (any(term in key.split() for term in processed_terms) or
            ("zon" in key.split() and "tomaten" in key.split())):
        if "onbewerkt" in hierarchy_text or "onverwerkt" in hierarchy_text:
            flags.append("Bewerkt product met GS1-klasse voor onbewerkt product")
    if "biet" in key and "koolsoorten" in hierarchy_text:
        flags.append("Rode biet is niet de GS1-klasse Koolsoorten")
    if "assortiment" in hierarchy_text and "assort" not in key:
        flags.append("Assortimentklasse voor afzonderlijk artikel")
    if norm(category) == "snack" and "onbewerkt" in hierarchy_text:
        flags.append("Snack/kroepoek is geen onbehandelde grondstof")
    if norm(category) == "babyvoeding" and "onbewerkt" in hierarchy_text:
        flags.append("Mogelijke babyvoeding; vers fruit mag niet stilzwijgend worden aangenomen")

    # Het lokale synoniemenbestand is niet volledig betrouwbaar: Chocopops
    # staat daar als hagelslag, hoewel graanproducten plausibel zijn.
    cereal_exception = "chocopops" in key and "graan" in hierarchy_text
    if (norm(category) in category_family_hints
            and not compatible_with_category(category, official)
            and not cereal_exception):
        flags.append("GS1-hierarchie wijkt af van voorlopige lokale productrichting")
    return list(dict.fromkeys(flags))


def off_direction(category_tags):
    """OPEN FOOD FACTS-context, nadrukkelijk geen GS1-code of certificering."""
    known = {
        "en:cheeses": "Zuivel / kaas",
        "en:milks": "Zuivel / melk",
        "en:yogurts": "Zuivel / yoghurt",
        "en:soft-drinks": "Dranken / frisdrank",
        "en:fruit-juices": "Dranken / vruchtensap",
        "en:teas": "Dranken / thee",
        "en:vegetables": "Groente",
        "en:fruits": "Fruit",
        "en:breads": "Bakkerij / brood",
        "en:pastas": "Pasta",
        "en:meats": "Vlees",
        "en:snacks": "Snacks",
    }
    candidates = {known[tag] for tag in category_tags if tag in known}
    return ", ".join(sorted(candidates)) if len(candidates) == 1 else (
        "Meerdere mogelijke OFF-richtingen" if candidates else "Niet uit OFF afleidbaar"
    )


def classify(name, linked_ids):
    category, local_explanation = seed_context(name)
    codes = {code for product_id in linked_ids for code in product_gpc.get(product_id, set())}
    if len(codes) == 1:
        code = next(iter(codes))
        flags = quality_flags(name, category, gpc_by_code[code])
        if flags:
            return ("BESTAAND_CONTROLEREN", code, hierarchy(code),
                    "; ".join(flags), category)
        return ("BESTAAND_CODE", code, hierarchy(code),
                "Bestaande officiële code; inhoudelijke juistheid niet bevestigd", category)
    if len(codes) > 1:
        return "CONFLICT", "", "", "Meerdere verschillende huidige GS1-codes", category

    head = composite_head(name)
    if head:
        return ("SAMENGESTELD_REVIEW", "", "",
                "Hele artikel beoordelen (" + head + "); geen GS1-klasse uit los ingrediënt", category)

    # Zonder een tweede, onafhankelijke productrichting kan een woordbotsing
    # (bijv. crackers/feestartikelen) geen officiële classificatie opleveren.
    if norm(category) not in food_categories:
        if category:
            return "ALLEEN_RICHTING", "", "", (
                "Lokale herkenning: " + local_explanation + "; geen officiële GS1-code"
            ), category
        return "ONBEKEND", "", "", "Te weinig betrouwbaar productbewijs", ""

    verified = seed_verified.get(norm(name))
    if verified and compatible_with_category(category, gpc_by_code[verified]):
        return ("REFERENTIE_BRICK", verified, hierarchy(verified),
                "Expliciete bestaande lokale verificatie; nog steeds geen opslag", category)

    proposal = suggestion(name, category)
    if proposal:
        official = gpc_by_code.get(str(proposal.get("brick_code") or "")) or {}
        if compatible_with_category(category, official) and not quality_flags(name, category, official):
            source_words = {word for word in norm(name).split()
                            if len(word) >= 4 and word not in ignored}
            official_words = set(norm(" ".join(str(official.get(field) or "") for field in (
                "gpc_brick_name", "gpc_class_name"
            ))).split())
            if source_words & official_words:
                return ("KLASSE_VOORSTEL", "", class_hierarchy(official),
                        "Officiële GS1-klasse als voorstel; Brick te onzeker; "
                        + ("meerdere kandidaten" if proposal.get("ambiguous") else "geen bevestiging"),
                        category)
    return ("ALLEEN_RICHTING", "", "",
            "Lokale productrichting herkend, maar geen betrouwbare officiële GS1-klasse", category)


stats = collections.defaultdict(collections.Counter)
paths = collections.Counter()
entries = []
lookup_priorities = []

for product in products:
    name = safe(product.get("name"), 110)
    product_id = str(product.get("id") or "")
    status, code, path, note, category = classify(name, {product_id})
    stats["Catalogus"][status] += 1
    if status == "BESTAAND_CODE":
        paths[path.split(" > ")[0]] += 1
    gtin = str(product.get("primary_gtin") or "").strip()
    safe_gtin = gtin if is_valid_gtin(gtin) else ""
    entries.append(("Catalogus", name, "", status, category, code, path, note, safe_gtin))
    if safe_gtin:
        priority = 1 if status == "BESTAAND_CONTROLEREN" else 2 if status == "ONBEKEND" else 4
        lookup_priorities.append((priority, safe_gtin))

for item in overview.get("items") or []:
    name = safe(item.get("receipt_line_text"), 110)
    gtin = str(item.get("article_code") or "").strip()
    linked_ids = gtin_products.get(gtin, set()) if gtin else set()
    status, code, path, note, category = classify(name, linked_ids)
    stats["Bonartikelen ED2"][status] += 1
    safe_gtin = gtin if is_valid_gtin(gtin) else ""
    entries.append((
        "Bonartikelen ED2", name, safe(item.get("retailer_code"), 40),
        status, category, code, path, note, safe_gtin,
    ))
    if safe_gtin:
        priority = 0 if item.get("link_status") == "classification_pending" else 3
        lookup_priorities.append((priority, safe_gtin))


# Een bonartikelnummer is GEEN barcode. Er is alleen een OFF-opvraag voor een
# door de bestaande Inhuis-code gevalideerde Catalogus-GTIN. De OFF-service is
# aantoonbaar read-only en verstrekt GEEN officiële GS1-classificatie.
# Om de publieke bron te ontzien: hoogstens zes product-GETs, zonder retries,
# 6 seconden tussen requests. Falen of lege categorieën blokkeren de proef niet.
off_evidence = {}
off_summary = collections.Counter()
max_off_requests = 6
known_gtins = sorted(set(gtin for _, gtin in lookup_priorities))
selected_gtins = []
for _, candidate_gtin in sorted(set(lookup_priorities)):
    if candidate_gtin not in selected_gtins:
        selected_gtins.append(candidate_gtin)
    if len(selected_gtins) >= max_off_requests:
        break
try:
    os.environ["REZZERV_OFF_SEARCH_TIMEOUT_SECONDS"] = "5"
    from app.services.off_search_service import lookup_off_product_by_gtin
except Exception as exc:
    lookup_off_product_by_gtin = None
    off_summary["service_niet_beschikbaar"] += 1

if lookup_off_product_by_gtin is not None:
    import time
    for index, gtin in enumerate(selected_gtins):
        if index:
            time.sleep(6)
        try:
            result = lookup_off_product_by_gtin(gtin)
            if result.get("mutated") is not False:
                raise RuntimeError("OFF-antwoord heeft geen expliciet read-only bewijs")
            status = str(result.get("status") or "onbekend")
            product = result.get("product") or {}
            off_summary[status] += 1
            off_evidence[gtin] = {
                "status": status,
                "name": safe(product.get("product_name"), 70),
                "category": safe(product.get("categories"), 110),
                "direction": off_direction(product.get("category_tags") or []),
            }
        except Exception:
            off_summary["netwerk_of_bronfout"] += 1
            off_evidence[gtin] = {"status": "niet_beschikbaar"}

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
print("============================================================")
print("INHUIS - TAXONOMIE-EERST - BEWIJS EN TEGENSPRAAK - PROEF 3")
print("============================================================")
print("Datum:", now)
print("Referentie: Nederlandse GS1 GPC", reference.get("publication_version"))
print("Beschikbare officiële Bricks:", len(gpc_by_code))
print("Database: PostgreSQL, TRANSACTION READ ONLY")
print("OFF: hoogstens 6 read-only GTIN-opvragen, 6 seconden tussen opvragen, geen retries")
print("OFF-productcategorieen dienen uitsluitend als extern referentiebewijs; geen automatische GS1-code")
print("Wijzigingen aan database, bonnen, voorraad, Artikelgroepen: GEEN")
print("HOOFDREGEL: een lokale productrichting is GEEN officiële GS1-classificatie.")
print("HOOFDREGEL: een GS1-klasse-voorstel is GEEN Brick-code en wordt nooit opgeslagen.")
print("Bestaande GS1-codes zijn niet automatisch inhoudelijk juist: controleer waarschuwingen.")
print("Een productgroep is NIET hetzelfde als een consumptietype voor Bijna op.")
print()
print("SAMENVATTING - ALLE ARTIKELEN")
for source in ("Catalogus", "Bonartikelen ED2"):
    row = stats[source]
    print(f"{source}: {sum(row.values())} artikelen")
    print(f"  Bestaande GS1-code (niet inhoudelijk getoetst): {row['BESTAAND_CODE']}")
    print(f"  Bestaande GS1-code, waarschuwing:               {row['BESTAAND_CONTROLEREN']}")
    print(f"  GS1-klasse als voorstel, GEEN Brick:            {row['KLASSE_VOORSTEL']}")
    print(f"  Samengesteld product, eerst beoordelen:        {row['SAMENGESTELD_REVIEW']}")
    print(f"  Referentie-Brick, nog geen opslag:              {row['REFERENTIE_BRICK']}")
    print(f"  Alleen lokale productrichting:                 {row['ALLEEN_RICHTING']}")
    print(f"  Geen betrouwbare productrichting:             {row['ONBEKEND']}")
    print(f"  Meerdere bestaande GS1-codes:                  {row['CONFLICT']}")
print("ED2 status (bestaande koppelingen):", overview.get("counts") or {})
print("Beschikbare gevalideerde Catalogusbarcodes:", len(known_gtins))
print("OFF opgevraagd:", len(off_evidence), "van maximaal", max_off_requests)
print("OFF-uitkomsten:", dict(off_summary))
print("LET OP: Catalogus en ED2 zijn afzonderlijke tellingen met mogelijke overlap.")
print()
print("ALLE BEOORDEELDE ARTIKELEN (GEEN DATABASEMUTATIES)")
print("Bron | Artikel | Winkel | Resultaat | Lokale richting (GEEN GS1) | GS1 Brick (alleen bestaand/referentie) | GS1-hierarchie (voorstel of bestaand) | Uitleg | GTIN Catalogus | OFF resultaat (indien geraadpleegd)")
for entry in entries:
    gtin = entry[-1]
    off = off_evidence.get(gtin, {})
    off_note = (off.get("status", "niet_opgevraagd") + ": " +
                off.get("name", "") + " / " + off.get("category", "") +
                " / OFF-richting: " + off.get("direction", "")) if gtin else "geen gevalideerde barcode"
    print(" | ".join(safe(part, 200) for part in (*entry, off_note)))
print()
print("GESLAAGD: alle beschikbare platformartikelen alleen-lezen beoordeeld.")
