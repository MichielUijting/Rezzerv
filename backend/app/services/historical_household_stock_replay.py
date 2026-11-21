"""Pure chronological historical-purchase replay for a *household's* stock.

No SQL/IO, no inferred identity, no manual confirmation and no writes. This
engine mirrors the live product-day modes: NONE adds, purchased-quantity
consumes old stock up to the new purchase, all-existing replaces old stock.
Confirmed synonym groups are supplied by the existing SQL authority.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Mapping, Sequence

from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_NONE,
    AUTO_CONSUME_PURCHASED_QUANTITY,
    AUTO_CONSUME_ALL_EXISTING,
)

MODES = frozenset((AUTO_CONSUME_NONE, AUTO_CONSUME_PURCHASED_QUANTITY,
                   AUTO_CONSUME_ALL_EXISTING))
MAX_HISTORICAL_PURCHASE_LINES = 20000
# One repeat purchase means two distinct purchase dates. There are no
# minimum observation spans, recency requirements, or gap thresholds.
MIN_PURCHASE_DAYS = 2


def _day(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value or "")[:10])


def _whole_positive(value) -> int:
    if isinstance(value, bool):
        raise ValueError("Boolean is geen voorraadaantal")
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Niet-numerieke aankoophoeveelheid") from exc
    if not number.is_finite() or number <= 0 or number != number.to_integral_value() or number > 10000:
        raise ValueError("Historische aankoop moet een geheel aantal stuks zijn")
    return int(number)


def _factor(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Ongeldige synoniemverpakkingsgrootte") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("Synoniemen vereisen aantoonbaar positieve verpakkingsgrootte")
    return number


def replay_historical_stock(
    *,
    household_id: str,
    cutoff: date,
    purchases: Sequence[dict],
    modes: Mapping[str, str],
    synonym_groups: Mapping[str, tuple[str, ...]] | None = None,
    package_sizes: Mapping[str, Decimal] | None = None,
) -> dict:
    """Return deterministic integer package stock by immutable household ID.

    purchases contain only already proven, physical, household-owned article
    identities. Each input includes household_id, household_article_id,
    purchase_date, quantity, receipt_id, line_id, raw_sha.

    synonym_groups map article ID -> the same confirmed component tuple,
    package_sizes specify exact catalog quantity per package for each member.
    The source loader must deny ambiguous/incompatible groups before calling.
    The replay revalidates group consistency and does not equate names or SKUs.
    """
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Actief regulier huishouden vereist")
    limit = len(purchases)
    if limit > MAX_HISTORICAL_PURCHASE_LINES:
        raise ValueError("Te veel historische aankoopregels; geen voorraadmutatie")
    target = _day(cutoff)
    groups = synonym_groups or {}
    factors = package_sizes or {}
    canonical_groups = {}
    for article, member_ids in groups.items():
        member_tuple = tuple(sorted(set(str(a).strip() for a in member_ids)))
        if str(article) not in member_tuple or not all(member_tuple):
            raise ValueError("Ongeldige bevestigde synoniemgroep")
        for member in member_tuple:
            prior = canonical_groups.setdefault(member, member_tuple)
            if prior != member_tuple:
                raise ValueError("Conflicterende synoniemcomponenten")
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    receipt_sha_owner = {}
    unique_lines = set()
    excluded_duplicate_receipts = 0
    source_count = 0
    source_evidence = []

    # Sort by actual purchase day, never by order of arrival or UI order.
    ordered = sorted(purchases, key=lambda r: (
        str(r.get("purchase_date") or "")[:10],
        str(r.get("receipt_id") or ""),
        str(r.get("line_id") or ""),
    ))
    for item in ordered:
        if str(item.get("household_id") or "") != owner:
            raise ValueError("Historische aankoop uit ander huishouden")
        day = _day(item.get("purchase_date"))
        if day >= target:
            raise ValueError("Actuele bon mag niet als historische voorraad tellen")
        article = str(item.get("household_article_id") or "").strip()
        rid = str(item.get("receipt_id") or "").strip()
        lid = str(item.get("line_id") or "").strip()
        sha = str(item.get("raw_sha") or "").strip().lower()
        if not article or not rid or not lid or not sha:
            raise ValueError("Historische voorraad vereist herleidbaar bronbewijs")
        unique_key = (rid, lid)
        if unique_key in unique_lines:
            raise ValueError("Dubbele bronregelidentiteit")
        unique_lines.add(unique_key)
        source = receipt_sha_owner.setdefault(sha, rid)
        if source != rid:
            excluded_duplicate_receipts += 1
            continue
        quantity = _whole_positive(item.get("quantity"))
        if article not in modes or modes[article] not in MODES:
            raise ValueError("Huishoudartikel heeft geen canonieke automodus")

        group = canonical_groups.get(article, (article,))
        if len(group) > 1:
            member_modes = {modes.get(member) for member in group}
            if member_modes not in ({AUTO_CONSUME_NONE}, {AUTO_CONSUME_PURCHASED_QUANTITY},
                                    {AUTO_CONSUME_ALL_EXISTING}):
                raise ValueError("Synoniemgroep bevat afwijkende artikelinstellingen")
            for member in group:
                if member not in factors:
                    raise ValueError("Ontbrekende Catalogusverpakking bij synoniemen")
                _factor(factors[member])
        group_key = tuple(group)
        grouped[group_key][day][article] += quantity
        source_evidence.append((day.isoformat(), article, quantity, rid, lid, sha))
        source_count += 1

    quantities = defaultdict(int)
    last_date = {}
    purchase_cadences = {}
    for members, per_day in sorted(grouped.items(), key=lambda it: it[0]):
        mode = modes[members[0]]
        dates = sorted(per_day)
        # A single *repeat* purchase suffices: two distinct dates.
        # Same-day receipts, even across stores and confirmed synonyms,
        # count as one occasion. Each next day updates the mean over all
        # consecutive intervals, without imposing recency or span filters.
        if len(dates) >= MIN_PURCHASE_DAYS:
            span = (dates[-1] - dates[0]).days
            evidence = {
                "average_repurchase_interval_days": round(span / (len(dates) - 1), 3),
                "purchase_day_count": len(dates),
                "first_purchase_date": dates[0].isoformat(),
                "last_purchase_date": dates[-1].isoformat(),
                "basis": "historical_confirmed_identity",
                "matched_and_synonyms": list(members),
            }
            for member in members:
                purchase_cadences[member] = evidence.copy()
        # Every member of a confirmed component is a potential stock identity;
        # a prior variant replaced by the last purchase can legitimately be 0.
        for member in members:
            quantities.setdefault(member, 0)
        sizes = {
            member: (_factor(factors[member]) if len(members) > 1 else Decimal("1"))
            for member in members
        }
        for day in sorted(per_day):
            buying = per_day[day]
            if mode == AUTO_CONSUME_ALL_EXISTING:
                for member in members:
                    quantities[member] = 0
            elif mode == AUTO_CONSUME_PURCHASED_QUANTITY:
                requested = sum(
                    Decimal(amount) * sizes[member]
                    for member, amount in buying.items()
                )
                # Existing synonym deduction prioritizes other variants.
                non_purchased = sorted(m for m in members if m not in buying)
                purchased = sorted(m for m in members if m in buying)
                for member in non_purchased + purchased:
                    old = quantities[member]
                    deduction = min(old, int(requested // sizes[member]))
                    quantities[member] -= deduction
                    requested -= Decimal(deduction) * sizes[member]
            for member, amount in buying.items():
                quantities[member] += amount
                last_date[member] = day.isoformat()

    return {
        "household_id": owner,
        "first_current_purchase_date": target.isoformat(),
        "source_line_count": source_count,
        "source_fingerprint": sha256(json.dumps({
            "cutoff": target.isoformat(),
            "events": source_evidence,
            "modes": sorted((article_id, modes[article_id]) for article_id in modes),
            "groups": sorted((aid, group) for aid, group in canonical_groups.items()),
            "sizes": sorted((aid, str(_factor(size))) for aid, size in factors.items()),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "excluded_duplicate_receipt_lines": excluded_duplicate_receipts,
        "quantities": dict(sorted(quantities.items())),
        "last_purchase_dates": last_date,
        "purchase_cadences": dict(sorted(purchase_cadences.items())),
        "writes_inventory": False,
        "policy_modes": {
            article_id: modes[article_id]
            for article_id in sorted(quantities)
        },
    }
