"""Read-only Bijna op bridge for persisted, confirmed household purchase cadence.

PR3 remains the writer and identity authority for the historic/current calendar.
A cadence alone is not consumption evidence: this bridge requires *actual*
purchase quantity for the cadence's latest day and current physical stock before
a prediction can influence Bijna op.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import math

from sqlalchemy import bindparam, text


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        raw = str(value or "").strip()
        return date.fromisoformat(raw[:10]) if len(raw) >= 10 else None
    except (TypeError, ValueError):
        return None


def load_confirmed_purchase_cadences(conn, household_id: str, articles) -> dict:
    """One household-scoped prefetch; never join a foreign/suspended article.

    Only complete, internally consistent confirmed synonym groups may be
    projected. Inactive, missing, conflicting, or foreign members fail closed.
    """
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        return {}
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        return {}
    active_ids = {
        str(row["id"])
        for row in articles
        if row.get("id") and str(row.get("status") or "active") == "active"
    }
    if not active_ids:
        return {}
    data = conn.execute(text("""
        SELECT c.household_article_id, c.average_repurchase_interval_days,
               c.purchase_day_count, c.first_purchase_date, c.last_purchase_date,
               c.matched_and_synonyms
        FROM household_historical_purchase_cadences c
        JOIN household_articles ha
          ON ha.id = c.household_article_id
         AND ha.household_id = c.household_id
         AND COALESCE(ha.status, 'active') = 'active'
        WHERE c.household_id = :household_id
          AND c.household_article_id IN :article_ids
    """).bindparams(bindparam("article_ids", expanding=True)), {
        "household_id": owner, "article_ids": sorted(active_ids),
    }).mappings().all()
    parsed = {}
    for entry in data:
        row = dict(entry)
        member_id = str(row.get("household_article_id") or "").strip()
        try:
            members_raw = json.loads(str(row.get("matched_and_synonyms") or ""))
            members = tuple(sorted(members_raw))
            interval = float(row["average_repurchase_interval_days"])
            count = int(row["purchase_day_count"])
        except (ValueError, TypeError, KeyError):
            continue
        first = _date(row.get("first_purchase_date"))
        last = _date(row.get("last_purchase_date"))
        if (not isinstance(members_raw, list) or not members
                or any(not isinstance(x, str) or not x.strip() for x in members_raw)
                or len(set(members)) != len(members)
                or member_id not in members or not set(members).issubset(active_ids)
                or count < 2 or not math.isfinite(interval) or interval <= 0
                or first is None or last is None or last <= first):
            continue
        parsed[member_id] = {
            "members": members, "interval_days": interval,
            "purchase_day_count": count, "first_date": first, "last_date": last,
        }
    # Require evidence for every member and identical canonical chronology:
    # partial membership must not predict combined stock.
    confirmed = {}
    for article_id, cadence in parsed.items():
        if all(parsed.get(member) == cadence for member in cadence["members"]):
            confirmed[article_id] = cadence
    return confirmed


def prediction_from_confirmed_cadence(
    cadence, purchase_events, prediction_days, *, current_quantity,
    minimum_stock=0, member_article_ids=(), now=None,
):
    """Forecast only with trusted latest-day purchase *volume* and current stock.

    Two purchase days (one repeat) establish the interval in PR3. The same
    persisted latest purchase day must have a real purchase/auto_repurchase
    inventory event with the exact authorized household-article identity.
    An older/stale cadence or a label-only event never provides a forecast.
    """
    if not cadence:
        return None
    try:
        interval = float(cadence["interval_days"])
        count = int(cadence["purchase_day_count"])
        stock = float(current_quantity)
        minimum = float(minimum_stock)
        horizon = int(prediction_days)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    members = set(cadence.get("members") or [])
    selected = set(str(x) for x in member_article_ids if str(x))
    if (count < 2 or not math.isfinite(interval) or interval <= 0
            or not all(math.isfinite(x) for x in (stock, minimum))
            or stock < 0 or minimum < 0 or horizon <= 0 or not members
            or members != selected):
        return None
    last = _date(cadence.get("last_date"))
    now_date = _date(now) if now is not None else datetime.now(timezone.utc).date()
    if last is None or now_date is None or last > now_date:
        return None
    observed = 0.0
    found = False
    for event in purchase_events:
        if event.get("event_type") not in {"purchase", "auto_repurchase"}:
            continue
        if str(event.get("article_id") or "") not in selected:
            continue
        day = _date(event.get("purchase_date"))
        if day is None:
            continue
        # The worker has not yet stored a later purchase: do not forecast
        # against stale cadence and do not double count same-day occasions.
        if day > last:
            return None
        if day != last:
            continue
        try:
            quantity = float(event.get("quantity"))
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(quantity) or quantity <= 0:
            return None
        observed += quantity
        found = True
    if not found or not math.isfinite(observed):
        return None
    rate = observed / interval
    if rate <= 0 or not math.isfinite(rate):
        return None
    projected = stock - rate * horizon
    if not math.isfinite(projected):
        return None
    remaining_days = max((stock - minimum) / rate, 0.0)
    if not math.isfinite(remaining_days):
        return None
    try:
        depletion = datetime.combine(now_date, time.min, tzinfo=timezone.utc) + timedelta(days=remaining_days)
    except (OverflowError, ValueError):
        return None
    return {
        "prediction_available": True,
        "prediction_basis": "confirmed_historical_cadence_and_latest_purchase_quantity",
        "average_purchase_interval_days": round(interval, 3),
        "average_purchase_quantity": None,  # One observed quantity is not a mean.
        "observed_latest_purchase_quantity": round(observed, 3),
        "last_purchase_at": last.isoformat() + "T00:00:00+00:00",
        "days_since_last_purchase": (now_date - last).days,
        "estimated_consumption_per_day": rate,
        "predicted_quantity_at_horizon": projected,
        "predicted_days_until_depletion": round(remaining_days, 3),
        "predicted_depletion_date": depletion.date().isoformat(),
        "predicted_depletion_at": depletion.isoformat(),
        "prediction_threshold_days": horizon,
        "prediction_triggered": projected <= minimum,
        "purchase_event_count": count,
    }


def prediction_from_untouched_historical_baseline(
    cadence, inventory_events, prediction_days, *, current_quantity,
    minimum_stock=0, member_article_ids=(), replacement_policy_proven=False,
    now=None,
):
    """Estimate depletion from historical opening stock *only* when verified.

    PR3's automatic stock writer persisted a special 'baseline' event for each
    proven household article. In the all-existing-replacement mode that baseline
    is the quantity bought on the latest historical product day. This may be
    used as an estimated replacement volume ONLY when:
      * Every confirmed synonym member has its original baseline event;
      * No later inventory/event mutation exists for the group;
      * Summed, converted baseline quantity agrees with the current stock;
      * The original household/article replacement policy is still proven.
    No such proof means no forecast. The purchase cadence alone is never enough.
    """
    if not cadence or not replacement_policy_proven:
        return None
    try:
        interval = float(cadence["interval_days"])
        count = int(cadence["purchase_day_count"])
        stock = float(current_quantity)
        minimum = float(minimum_stock)
        horizon = int(prediction_days)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    members = set(cadence.get("members") or [])
    selected = set(str(value) for value in member_article_ids if str(value))
    last = _date(cadence.get("last_date"))
    today = _date(now) if now is not None else datetime.now(timezone.utc).date()
    if (count < 2 or not math.isfinite(interval) or interval <= 0
            or not all(math.isfinite(value) for value in (stock, minimum))
            or stock <= 0 or minimum < 0 or horizon <= 0
            or not selected or members != selected or last is None
            or today is None or last > today):
        return None

    observed_by_article = {}
    for event in inventory_events:
        article = str(event.get("article_id") or "")
        if article not in selected:
            continue
        if (event.get("event_type") != "baseline"
                or event.get("source") != "historical_auto_stock"
                or article in observed_by_article):
            # An intervening purchase, consume, correction or second baseline
            # invalidates the assumption that current stock still is opening stock.
            return None
        try:
            quantity = float(event.get("quantity"))
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(quantity) or quantity < 0:
            return None
        observed_by_article[article] = quantity
    if set(observed_by_article) != selected:
        return None
    last_replacement = sum(observed_by_article.values())
    if (last_replacement <= 0 or not math.isfinite(last_replacement)
            or not math.isclose(last_replacement, stock, abs_tol=1e-6, rel_tol=0)):
        return None
    rate = last_replacement / interval
    elapsed = (today - last).days
    remaining = max((stock - minimum) / rate - elapsed, 0.0)
    predicted = stock - rate * (elapsed + horizon)
    if not all(math.isfinite(value) for value in (remaining, predicted)):
        return None
    try:
        depletion = datetime.combine(today, time.min, tzinfo=timezone.utc) + timedelta(days=remaining)
    except (ValueError, OverflowError):
        return None
    return {
        "prediction_available": True,
        "prediction_basis": "confirmed_historical_replacement_and_untouched_opening_stock",
        "average_purchase_interval_days": round(interval, 3),
        "average_purchase_quantity": None,
        "observed_historical_last_purchase_quantity": round(last_replacement, 3),
        "last_purchase_at": last.isoformat() + "T00:00:00+00:00",
        "days_since_last_purchase": elapsed,
        "estimated_consumption_per_day": rate,
        "predicted_quantity_at_horizon": predicted,
        "predicted_days_until_depletion": round(remaining, 3),
        "predicted_depletion_date": depletion.date().isoformat(),
        "predicted_depletion_at": depletion.isoformat(),
        "prediction_threshold_days": horizon,
        "prediction_triggered": predicted <= minimum,
        "purchase_event_count": count,
    }
