"""Pure, read-only product-group evidence helpers for Inhuis taxonomy proof 4.

The existing local vocabulary helps discover possible groups, but is never
treated as an official GS1 assignment or as a product identity match.
"""

import collections
import re
import unicodedata


def norm(value):
    folded = unicodedata.normalize("NFKD", str(value or "").casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def safe(value, limit=120):
    return " ".join(str(value or "").replace("|", "/").replace(";", ",").split())[:limit]


def store_key(value):
    key = norm(value)
    if key in {"ah", "albert heijn", "albert heijn bv"}:
        return "albert heijn"
    if key.startswith("lidl"):
        return "lidl"
    return key


def _contains_words(title, phrase):
    return bool(phrase) and (" " + phrase + " ") in (" " + title + " ")


# Unqualified description fragments are too broad for even a local proposal.
# A descriptor is safe only as part of a more specific multiword alias.
GENERIC_DESCRIPTORS = {
    "gerasp", "geraspt", "rasp", "volle", "vol", "jong", "jonge",
    "oud", "oude", "belegen", "naturel", "mix", "ontbijt", "maaltijd",
}
SHORT_PRODUCT_NOUNS = {"kaas", "prei", "soep", "mayo", "nasi", "bami", "kiwi"}

NON_PRODUCT_TERMS = {
    "pluspunten", "verzendkosten", "korting", "spaarzegels",
    "koopzegels", "statiegeld", "emballage", "po testartikel",
}


def build_seed_index(seed):
    """Index only data already provided by Inhuis; never learn from receipts."""
    by_intent = {row.get("intent_key"): row for row in seed.get("taxonomy") or []}
    aliases = []
    for item in seed.get("taxonomy") or []:
        group = safe(item.get("category"), 40)
        for alias in [item.get("canonical_name"), *(item.get("synonyms") or [])]:
            phrase = norm(alias)
            if (len(phrase) < 5 and phrase not in SHORT_PRODUCT_NOUNS) or phrase in GENERIC_DESCRIPTORS:
                continue
            aliases.append((phrase, group, str(item.get("intent_key") or "")))
    # The same alias can occur more than once; duplicates cannot add confidence.
    aliases = sorted(set(aliases), key=lambda row: (-len(row[0]), row[0], row[1]))

    receipt = collections.defaultdict(list)
    for item in seed.get("retailer_receipt_terms") or []:
        group_row = by_intent.get(item.get("intent_key")) or {}
        phrase = norm(item.get("receipt_term"))
        retailer = store_key(item.get("retailer_code"))
        if phrase and retailer and group_row and float(item.get("confidence") or 0) >= 0.85:
            receipt[(retailer, phrase)].append((
                safe(group_row.get("category"), 40),
                safe(item.get("normalized_term"), 70),
                safe(item.get("source"), 60),
            ))
    return {"aliases": aliases, "receipt": receipt}


def group_direction(name, retailer, index):
    """Return local *hypothesis*, including conflicts and provenance."""
    title = norm(name)
    if not title or title in NON_PRODUCT_TERMS:
        return {"group": "", "evidence": "Geen productbewijs", "conflict": False}

    specific = index["receipt"].get((store_key(retailer), title)) or []
    if specific:
        groups = {group for group, _normalized, _source in specific}
        if len(groups) != 1:
            return {"group": "", "evidence": "Tegenstrijdige winkelafkortingen", "conflict": True}
        group, normalized, source = specific[0]
        return {
            "group": group,
            "evidence": "Winkelafkorting uit bestaande Inhuis-referentie: " + normalized
                        + " (" + source + ")",
            "conflict": False,
        }

    matches = []
    for phrase, group, _intent in index["aliases"]:
        exact_words = _contains_words(title, phrase)
        # Concatenated retail compounds such as 'trostomaat' and 'risottorijst'
        # are recognizable by a specific headword, not by short generic words.
        safe_suffix = (" " not in phrase and len(phrase) >= 5 and any(
            word.endswith(phrase) for word in title.split()
        ))
        if exact_words or safe_suffix:
            matches.append((len(phrase), group, phrase))
    if not matches:
        return {"group": "", "evidence": "Geen bestaande woordenlijstmatch", "conflict": False}

    # Keep only near-best aliases to avoid a generic ingredient deciding the
    # category of a prepared composite product (e.g. cheese in a cheese pizza).
    best_length = max(length for length, _group, _term in matches)
    strongest = [(group, phrase) for length, group, phrase in matches
                 if length >= max(5, int(best_length * 0.80))]
    groups = {group for group, _phrase in strongest}
    if len(groups) != 1:
        return {
            "group": "", "evidence": "Meerdere productrichtingen: "
                + ", ".join(sorted(groups)), "conflict": True,
        }
    group = next(iter(groups))
    term = sorted((phrase for found_group, phrase in strongest if found_group == group),
                  key=lambda value: (-len(value), value))[0]
    return {"group": group, "evidence": "Lokale woordenlijst: " + term,
            "conflict": False}


def _signature(name):
    title = " " + norm(name) + " "
    signatures = (
        (("kerrie", "venkelzaad", "rosmarijn", "rozemarijn", "cayennepeper"),
         ("kruiden", "specerijen", "extracten"), "Kruiden/specerijen"),
        (("chorizo", "grillworst", "rookworst", "salami", "cervelaat"),
         ("vlees", "worst", "gevogelte"), "Vleeswaren"),
        (("chocopops", "ontbijt granen", "ontbijtgranen", "choco shells"),
         ("graan", "ontbijt"), "Ontbijtgranen"),
        (("pepita", "amandelen", "hazelnoten"),
         ("noten", "zaad"), "Noten/zaden"),
    )
    for terms, clues, label in signatures:
        if any(_contains_words(title.strip(), norm(term)) for term in terms):
            return clues, label
    return (), ""


def existing_code_warnings(name, direction, official):
    """Flag contradictions; absence of a flag is NOT code validation."""
    category = norm(direction.get("group"))
    combined = norm(" ".join(str(official.get(key) or "") for key in (
        "gpc_segment_name", "gpc_family_name", "gpc_class_name", "gpc_brick_name"
    )))
    title = norm(name)
    warnings = []
    food_direction = category not in {"", "huishouden", "non food", "nonfood"}
    clues, label = _signature(name)
    if (food_direction or clues) and str(official.get("gpc_segment_code") or "") != "50000000":
        warnings.append("Voedingsartikel buiten het GS1-voedselsegment")
    if clues and not any(term in combined for term in clues):
        warnings.append(label + " wijkt af van de bestaande Brick")
    if "aardappelschijfje" in title and "stengels van de zoete aardappel" in combined:
        warnings.append("Aardappelschijfjes zijn geen stengels van de zoete aardappel")
    if "frites" in title and ("onbewerkt" in combined or "onverwerkt" in combined):
        warnings.append("Frites als onbewerkte aardappelen ingedeeld")
    if "ontbijt granen" in title and "maaltijden op basis van groenten" in combined:
        warnings.append("Ontbijtgranen als groentemaaltijd ingedeeld")
    if "babyvoeding" == category and "onbewerkt" in combined:
        warnings.append("Babyvoeding lijkt als onbewerkt fruit ingedeeld")
    if "assortiment" in combined and "assort" not in title:
        warnings.append("Assortimentklasse voor afzonderlijk product")
    return list(dict.fromkeys(warnings))


def build_gpc_classes(reference):
    classes = {}
    for item in reference.get("bricks") or []:
        class_code = str(item.get("gpc_class_code") or "")
        if class_code and class_code not in classes:
            classes[class_code] = item
    return tuple(classes.values())


def family_group(family, gpc_class="", brick_name=""):
    """Dutch display group based on an *official GS1 family name*.

    This mapping is only a coarse reporting label. It is not an Inhuis
    Producttype, household Artikelgroep, or an official new GS1 level.
    Mixed families are deliberately left unclassified.
    """
    value = norm(family)
    gpc_class_key = norm(gpc_class)
    if gpc_class_key == "verse kruiden":
        return "Kruiden/smaakmakers"
    if ("botervervanger" in gpc_class_key or "margarine" in gpc_class_key
            or "margarine" in norm(brick_name)):
        return "Vetten/oliën"
    if "sauzen" in gpc_class_key or "dressing" in gpc_class_key:
        return "Saus"
    if "groenten niet blad" in value or "bladgroenten" in value:
        return "Groente"
    if value.startswith("fruit onbewerkt") or value.startswith("fruit niet bereid"):
        return "Fruit"
    if "melk boter room yoghurt kaas eieren" in value:
        return "Zuivel/alternatieven"
    if value == "dranken":
        return "Drank"
    if value.startswith("vlees gevogelte wild"):
        return "Vlees"
    if "vis schaaldieren schelpdieren" in value:
        return "Vis"
    if "brood bakkerij" in value:
        return "Bakkerij"
    if value.startswith("graanproducten peulvruchtproducten"):
        return "Graan/peulvrucht"
    if value.startswith("kruiden conserveringsmiddelen extracten"):
        return "Kruiden/smaakmakers"
    return ""


def _brick_core_words(title):
    # Distinguishing retail product head, excluding packaging and condition.
    value = re.split(r"[(/]", str(title or ""), maxsplit=1)[0]
    value = value.split(" - ", 1)[0]
    value = norm(value)
    generic = {
        "producten", "product", "andere", "overige", "assortimenten",
        "groenten", "fruiten", "fruit", "snacks", "vlees", "soepen",
        "bereide", "bewerkte", "kruiden", "zaden", "noten", "dranken",
        "vers", "onbewerkt", "verwerkt", "niet", "houdbaar",
    }
    if value in generic or len(value) < 6:
        return ""
    return value


def build_brick_term_index(reference):
    """Index official food Brick *names*, not local name-to-code rules."""
    lookup = collections.defaultdict(list)
    for item in reference.get("bricks") or []:
        if str(item.get("gpc_segment_code") or "") != "50000000":
            continue
        group = family_group(item.get("gpc_family_name"), item.get("gpc_class_name"),
                             item.get("gpc_brick_name"))
        core = _brick_core_words(item.get("gpc_brick_name"))
        if group and core:
            lookup[core].append((group, safe(item.get("gpc_class_name"), 70)))
    return lookup


def gs1_word_hypothesis(name, lookup):
    """A name overlap with the official taxonomy, NEVER a GTIN or GPC match."""
    title = norm(name)
    if not title or title in NON_PRODUCT_TERMS:
        return {"group": "", "evidence": "", "conflict": False}
    if any(token in title.split() for token in ("plant", "potplant", "zaden", "stek")):
        # A grocery item might be fresh herbs, but a plant is not automatically food.
        return {"group": "", "evidence": "", "conflict": False}
    if ("in pot" in title or "potplant" in title) and any(term in title for term in (
            "basilicum", "rozemarijn", "oregano", "peterselie")):
        return {"group": "", "evidence": "Kruidenplant of consumptieproduct onbekend", "conflict": False}
    hits = [(len(core), core, group, gpc_class)
            for core, values in lookup.items() if _contains_words(title, core)
            for group, gpc_class in values]
    if not hits:
        return {"group": "", "evidence": "", "conflict": False}
    best = max(hit[0] for hit in hits)
    contenders = [row for row in hits if row[0] >= best * 0.85]
    # A retail name often contains an ingredient rather than the actual
    # product head; in that case a matched raw ingredient is not taxon proof.
    product_heads = ("crouton", "crout", "bladerdeeg", "pizza", "chips",
                     "kroepoek", "saus", "salade", "soep", "wrap", "brood")
    if any(head in title for head in product_heads) and not any(
            head in hit[1] for head in product_heads for hit in contenders):
        return {"group": "", "evidence": "Ingrediënt is geen heel product",
                "conflict": False}
    groups = {row[2] for row in contenders}
    if len(groups) != 1:
        return {"group": "", "evidence": "GS1-termen uit meerdere families", "conflict": True}
    canonical = sorted(contenders, key=lambda row: (-row[0], row[1], row[3]))[0]
    return {
        "group": canonical[2],
        "evidence": "Woordovereenkomst met officiële GS1 Brick-omschrijving: " + canonical[1]
                    + " (dit is GEEN bewezen Brick-koppeling)",
        "conflict": False,
    }


def combined_direction(name, retailer, local_index, official_term_index):
    local = group_direction(name, retailer, local_index)
    gs1 = gs1_word_hypothesis(name, official_term_index)
    title = norm(name)
    if (local["group"] in {"Groente", "Fruit", "Zuivel", "Vlees", "Vleeswaren"}
            and any(head in title for head in (
                "pizza", "ovenschotel", "crout", "croissant", "kroepoek", "lasagne"
            )) and "Lokale woordenlijst:" in local["evidence"]):
        local = {"group": "", "conflict": False,
                 "evidence": "Ingrediënt is niet automatisch het hele samengestelde artikel"}
    if local["conflict"] or gs1["conflict"]:
        return {"group": "", "conflict": True,
                "evidence": local["evidence"] + " / " + gs1["evidence"]}
    if local["group"] and gs1["group"]:
        # Some official family labels are deliberately wider than local groups.
        families = {
            "Zuivel": "Zuivel/alternatieven", "Eieren": "Zuivel/alternatieven",
            "Graan": "Graan/peulvrucht", "Peulvrucht": "Graan/peulvrucht",
            "Kruiden": "Kruiden/smaakmakers", "Saus": "Kruiden/smaakmakers",
            "Vleeswaren": "Vlees",
        }
        expected_group = families.get(local["group"], local["group"])
        if local["group"] == "Saus" and gs1["group"] == "Saus":
            expected_group = "Saus"
        if expected_group != gs1["group"]:
            return {"group": "", "conflict": True,
                    "evidence": "Lokale richting en GS1-familiewoord spreken elkaar tegen: "
                                + local["group"] + " / " + gs1["group"]}
        return {"group": local["group"], "conflict": False,
                "evidence": local["evidence"] + " + " + gs1["evidence"]}
    return local if local["group"] else gs1


def class_hypothesis(name, group, classes):
    """At most class-level indication; never return a Brick code."""
    if not group:
        return ""
    source = {token for token in norm(name).split() if len(token) >= 5}
    if not source:
        return ""
    matches = []
    for row in classes:
        if str(row.get("gpc_segment_code") or "") != "50000000":
            continue
        target = {word for word in norm(row.get("gpc_class_name")).split()
                  if len(word) >= 5}
        # Only exact descriptive terms from the actual item, no name guesses.
        shared = source & target
        if not shared:
            continue
        score = len(shared) / max(1, len(target))
        matches.append((score, row.get("gpc_class_code"), row))
    if not matches:
        return ""
    matches.sort(key=lambda value: (-value[0], str(value[1])))
    if len(matches) > 1 and matches[1][0] >= matches[0][0] * 0.90:
        return ""
    best = matches[0][2]
    return " > ".join(safe(best.get(key), 80) for key in (
        "gpc_segment_name", "gpc_family_name", "gpc_class_name"
    ) if best.get(key))
