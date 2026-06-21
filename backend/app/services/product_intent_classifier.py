from __future__ import annotations

import re


PRODUCT_INTENT_RULES: tuple[tuple[str, str], ...] = (
    # Eerst samengestelde termen, daarna generiekere termen.
    ("bananenvla", "zuivel.vla"),
    ("vla banaan", "zuivel.vla"),
    ("vla", "zuivel.vla"),

    ("pindakaas", "broodbeleg.notenpasta"),
    ("notenpasta", "broodbeleg.notenpasta"),

    ("hagelslag melk", "broodbeleg.hagelslag"),
    ("chocoladehagelslag", "broodbeleg.hagelslag"),
    ("hagelslag", "broodbeleg.hagelslag"),

    ("geraspte kaas", "zuivel.kaas"),
    ("jonge kaas", "zuivel.kaas"),
    ("belegen kaas", "zuivel.kaas"),
    ("oude kaas", "zuivel.kaas"),
    ("kaas 48", "zuivel.kaas"),
    ("kaas", "zuivel.kaas"),

    ("halfvolle melk", "zuivel.melk"),
    ("volle melk", "zuivel.melk"),
    ("magere melk", "zuivel.melk"),
    ("melk halfvol", "zuivel.melk"),
    ("melk vol", "zuivel.melk"),
    ("melk", "zuivel.melk"),

    ("banaan", "fruit.banaan"),
    ("bananen", "fruit.banaan"),

    ("elstar appels", "fruit.appel"),
    ("elstar appel", "fruit.appel"),
    ("appels", "fruit.appel"),
    ("appel", "fruit.appel"),

    ("volkoren brood", "bakkerij.brood"),
    ("brood", "bakkerij.brood"),

    ("spinazie diepvries", "groente.spinazie"),
    ("spinazie", "groente.spinazie"),

    ("pizza margherita", "maaltijd.pizza"),
    ("pizza", "maaltijd.pizza"),

    ("mexicaanse kruidenm", "kruiden.specerijenmix"),
    ("mexicaanse kruidenmix", "kruiden.specerijenmix"),
    ("taco specerijenmix", "kruiden.specerijenmix"),
    ("burrito specerijenmix", "kruiden.specerijenmix"),
    ("fajita specerijenmix", "kruiden.specerijenmix"),
    ("taco kruidenmix", "kruiden.specerijenmix"),
    ("burrito kruidenmix", "kruiden.specerijenmix"),
    ("fajita kruidenmix", "kruiden.specerijenmix"),
    ("seasoning mix", "kruiden.specerijenmix"),
    ("specerijenmix", "kruiden.specerijenmix"),
    ("kruidenmix", "kruiden.specerijenmix"),

    ("magere yoghurt", "zuivel.yoghurt"),
    ("yoghurt", "zuivel.yoghurt"),

    ("achterham", "vleeswaren.ham"),
    ("kipfilet plakken", "vleeswaren.kipfilet"),
    ("kipfilet", "vleeswaren.kipfilet"),

    ("cola zero", "drank.frisdrank"),
    ("cola", "drank.frisdrank"),
    ("frisdrank", "drank.frisdrank"),

    ("spaghetti", "pasta.droog"),
    ("penne rigate", "pasta.droog"),
    ("penne", "pasta.droog"),
    ("pasta", "pasta.droog"),

    ("naturel chips", "snack.chips"),
    ("chips", "snack.chips"),

    ("muesli naturel", "ontbijt.muesli"),
    ("muesli", "ontbijt.muesli"),

    ("havermout", "ontbijt.havermout"),

    ("mineraalwater", "drank.water"),
    ("water", "drank.water"),
)


def normalize_product_intent_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def classify_product_intent(text: str | None) -> str:
    normalized = normalize_product_intent_text(text)

    if not normalized:
        return ""

    for needle, intent in PRODUCT_INTENT_RULES:
        needle_normalized = normalize_product_intent_text(needle)
        if needle_normalized and needle_normalized in normalized:
            return intent

    return ""


def product_intent_match_score(receipt_text: str | None, candidate_text: str | None) -> float:
    receipt_intent = classify_product_intent(receipt_text)
    candidate_intent = classify_product_intent(candidate_text)

    if not receipt_intent or not candidate_intent:
        return 0.50

    if receipt_intent == candidate_intent:
        return 1.00

    return 0.00


def has_meaningful_product_intent_match(receipt_text: str | None, candidate_text: str | None) -> bool:
    receipt_intent = classify_product_intent(receipt_text)
    candidate_intent = classify_product_intent(candidate_text)

    # Onbekende intent blokkeert niet; dan blijft de gewone tekstscore leidend.
    if not receipt_intent or not candidate_intent:
        return True

    return receipt_intent == candidate_intent
