"""Conservatieve labelproef: Shopify + ECOICOP, uitsluitend voorstellen.

Het herkennen van een woord is geen productidentificatie. Geen enkel resultaat
mag zonder afzonderlijke goedkeuring worden opgeslagen als GS1, Producttype,
Artikelgroep of OFF-koppeling.
"""

from collections import defaultdict
import gzip
import json
import re
import unicodedata
from pathlib import Path


DATA = Path(__file__).resolve().parent / "taxonomy_proof5_references"
NOISE = {
    "producten", "product", "items", "item", "en", "voor", "met", "van",
    "andere", "overige", "de", "het", "een", "verschillende", "accessoires",
    "benodigdheden", "voedselitems", "drinken", "voeding", "verzorging",
    "diverse", "soorten", "producten", "dranken", "voedingsmiddelen",
    "in", "uit", "basis", "overig", "origineel", "original", "extra",
    "groot", "klein", "vers", "verse", "diepvries", "gerookt", "geraspte",
    "assortiment", "mix", "sets", "set", "kit", "artikel", "art",
}
SHOPIFY_PREFERRED = {"fb", "hg", "hb", "bt", "ap"}
COMPOSITE = {
    "ovenschotel", "pizza", "pizzas", "maaltijd", "salade", "soep",
    "saus", "wrap", "wok", "mix", "pasta", "smoothie", "kant", "klaar",
}
PROCESSING_WORDS = {"gezeefd", "gepureerd", "puree", "frites", "frieten",
                    "bereid", "gebakken", "geroosterd", "schnitzel", "gepaneerd",
                    "gedroogd", "saus", "gekookt", "ingelegd", "gekruid", "gekruide"}
HOMONYM_PHRASES = {"triangel", "snoep tomaat", "snoeptomaat"}
SHORT_PRODUCT_WORDS = {"ham", "prei", "melk", "bier", "kaas", "thee", "soep", "peer", "kip"}
RETAIL_PREFIXES = {"ah", "lidl", "jumbo", "plus", "aldi", "picnic", "de", "het"}

# Voorstel van verwantschap tussen twee openbare taxonomieen: geen officiële
# crosswalk en geen productbewijs. Alleen brede, inhoudelijk conservatieve
# bestedingscategorieën; nooit automatisch in Artikelgroep toepassen.
SHOPIFY_TO_ECO = (
    ("fb-2-10-8", "011700"),  # verse groenten
    ("fb-2-10-7", "011600"),  # vers fruit
    ("fb-2-10-4", "011670"),  # gedroogd fruit
    ("fb-2-10-6", "011760"),  # peulvruchten
    ("fb-2-10-5", "011770"),  # gedroogde groenten
    ("fb-2-6", "011400"),     # zuivel
    ("fb-1-9", "011400"),     # melk als drank
    ("fb-1-10", "011440"),    # plantaardige melk
    ("fb-2-11", "011100"),    # granen
    ("fb-2-1", "011130"),     # bakkerij, beperkt tot broodachtig niveau
    ("fb-2-12-1", "011480"),  # eieren
    ("fb-2-12-2", "011200"),  # vlees
    ("fb-2-12-3", "011300"),  # zeevruchten
    ("fb-1-12", "012600"),    # priklimonade
    ("fb-1-16", "012500"),    # water
    ("fb-2-14", "011150"),    # pasta en noedels
)


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", value)


def _singular(token):
    if len(token) >= 9 and token.endswith("en") and not token.endswith("eren"):
        return token[:-2]
    if len(token) >= 6 and token.endswith("s"):
        return token[:-1]
    return token


def _phrase_in(phrase_tokens, haystack_tokens):
    if not phrase_tokens or len(phrase_tokens) > len(haystack_tokens):
        return False
    phrase = [_singular(token) for token in phrase_tokens]
    haystack = [_singular(token) for token in haystack_tokens]
    width = len(phrase)
    return any(haystack[idx:idx + width] == phrase
               for idx in range(len(haystack) - width + 1))


def _category_words(name):
    words = _norm(re.sub(r"\([^)]*\)", "", name))
    if not words or len(words) > 6 or any(word in ("en", "of", "enof") for word in words):
        return ()
    if not any((len(word) >= 4 or word in SHORT_PRODUCT_WORDS)
               and word not in NOISE for word in words):
        return ()
    if len(words) == 1 and ((len(words[0]) < 5 and words[0] not in SHORT_PRODUCT_WORDS)
                           or words[0] in NOISE):
        return ()
    return tuple(words)


def load_references(data_dir=DATA):
    with gzip.open(Path(data_dir) / "shopify_2026_08_nl.json.gz", "rt", encoding="utf-8") as source:
        shopify = json.load(source)
    eco = json.loads((Path(data_dir) / "cbs_ecoicop_v2_2026.json").read_text(encoding="utf-8"))
    if shopify.get("versie") != "2026-08" or len(shopify.get("categorieen") or ()) != 14606:
        raise RuntimeError("VEILIG GESTOPT: Shopify-referentieversie of categorieaantal wijkt af")
    if len(eco.get("codes") or ()) != 440:
        raise RuntimeError("VEILIG GESTOPT: CBS ECOICOPv2-referentieaantal wijkt af")
    return shopify, eco


class Matcher:
    def __init__(self, shopify, eco):
        self.shopify = shopify
        self.eco = eco
        self.eco_codes = {row["code"]: row["naam"] for row in eco["codes"]}
        self.by_word = defaultdict(list)
        for category in shopify["categorieen"]:
            words = _category_words(category["naam"])
            if not words:
                continue
            anchor = max(words, key=len)
            self.by_word[_singular(anchor)].append((category, words))
        self.eco_exact = defaultdict(list)
        for row in eco["codes"]:
            words = _category_words(row["naam"])
            if words:
                self.eco_exact[_singular(max(words, key=len))].append((row, words))

    def match(self, name, retailer=""):
        tokens = _norm(name)
        if tokens and tokens[0] in RETAIL_PREFIXES:
            tokens = tokens[1:]
        candidates = []
        for word in set(map(_singular, tokens)):
            for category, phrase in self.by_word[word]:
                if not _phrase_in(phrase, tokens):
                    continue
                # Alleen letterlijke categorie-naam, niet willekeurige woorden
                # uit verre hiërarchische voorouders.
                score = sum(len(term) for term in phrase)
                if _phrase_in(phrase, tokens) and len(phrase) == len(tokens):
                    score += 100
                candidates.append((score, category))
        candidates.sort(key=lambda entry: (-entry[0], -len(entry[1]["id"]), entry[1]["id"]))
        highest = candidates[0][0] if candidates else 0
        best = [c for score, c in candidates if score == highest]
        # Echte dubbelzinnigheid blijft zichtbaar, nooit op eigen houtje kiezen.
        families = {"-".join(c["id"].split("-")[:3]) for c in best}
        direct = bool(best and highest >= 100 and len(families) == 1)
        has_composite = any(word in COMPOSITE for word in tokens)
        vegetable_as_ingredient = any(c["id"].startswith("fb-2-10") for c in best)
        vegetable_fresh = any(c["id"].startswith("fb-2-10-8") for c in best)
        name_text = " ".join(tokens)
        if name_text in HOMONYM_PHRASES:
            result = "HOMONIEM_CONTROLEREN"
        elif vegetable_fresh and any(token in PROCESSING_WORDS for token in tokens):
            result = "BEREIDINGSVORM_ONZEKER"
        elif has_composite and vegetable_as_ingredient:
            result = "INGREDIËNTGEVAAR"
        elif not candidates:
            result = "GEEN_VERANTWOORDE_MATCH"
        elif len(families) > 1:
            result = "MEERDUIDIGE_SHOPIFY_CATEGORIE"
        elif direct:
            result = "EXACTE_NAAM_VOORSTEL"
        else:
            result = "WOORDMATCH_CONTROLEREN"
        if best and not any(c["id"].split("-", 1)[0] in SHOPIFY_PREFERRED for c in best):
            # Een kassabonwoord als TRIANGEL kan ook brood zijn; geen bewijs
            # dat een identiek niet-voedingslabel daadwerkelijk het product is.
            result = "NONFOOD_CONTEXT_CONTROLEREN"

        direct_cbs = []
        for word in set(map(_singular, tokens)):
            for row, phrase in self.eco_exact[word]:
                if _phrase_in(phrase, tokens):
                    direct_cbs.append(row)
        direct_cbs.sort(key=lambda r: (-len(r["naam"]), r["code"]))

        crosswalk = set()
        for category in best:
            for prefix, code in SHOPIFY_TO_ECO:
                if category["id"] == prefix or category["id"].startswith(prefix + "-"):
                    if code in self.eco_codes:
                        crosswalk.add(code)
                    break
        return {
            "status": result,
            "shopify": best[:4],
            "shopify_extra": len(best) - min(len(best), 4),
            "cbs_letterlijk": direct_cbs[:3],
            "cbs_vergelijking": [(code, self.eco_codes[code]) for code in sorted(crosswalk)],
            "aantal_candidates": len(candidates),
        }


def off_evidence_tags(tags):
    """Referentie uit OFF-categorieën, nooit automatisch als GS1 of Shopify."""
    known = {
        "en:cheeses": "Zuivel / kaas", "en:milks": "Zuivel / melk",
        "en:yogurts": "Zuivel / yoghurt", "en:soft-drinks": "Dranken / frisdrank",
        "en:fruit-juices": "Dranken / sap", "en:vegetables": "Groente",
        "en:fruits": "Fruit", "en:breads": "Brood", "en:pastas": "Pasta",
        "en:meats": "Vlees", "en:snacks": "Snacks", "en:waters": "Water",
    }
    found = {known[tag] for tag in tags if tag in known}
    return ", ".join(sorted(found)) if found else "geen herkende OFF-richting"


def safe(value, length=155):
    return re.sub(r"[\r\n|]+", " ", str(value or ""))[:length]
