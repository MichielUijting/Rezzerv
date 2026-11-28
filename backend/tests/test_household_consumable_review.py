"""Protection of historical classification decisions and inferred review hints."""
from __future__ import annotations

import json
import pytest

from app.services.household_consumable_review import (
    ReviewConflict, ReviewNotFound, _state,
    list_consumable_review_candidates, record_explicit_consumable_review,
    ORIGIN_KEY, HISTORY_KEY,
)


def test_state_does_not_conflate_unknown_and_explicit_false():
    assert _state(None) == "unknown"
    assert _state(0) == "false"
    assert _state(False) == "false"
    assert _state(True) == "true"


class _Rows:
    def __init__(self, one=None, many=(), scalar=None, rowcount=1):
        self.one, self.many, self.value, self.rowcount = one, many, scalar, rowcount

    def mappings(self):
        return self

    def first(self):
        return self.one

    def all(self):
        return list(self.many)

    def scalar_one(self):
        return self.value


class _ReviewConn:
    def __init__(self, articles, settings=None):
        self.articles = dict(articles)
        self.settings = dict(settings or {})
        self.calls = []

    def execute(self, query, params):
        sql = str(query)
        self.calls.append((sql, dict(params)))
        if "FROM household_articles" in sql and "FOR UPDATE" in sql:
            assert params["household_id"] == "home-1"
            row = self.articles.get(params["article_id"])
            return _Rows(one=row)
        if "FROM household_article_settings" in sql and "FOR UPDATE" in sql:
            key = (params["article_id"], params["setting_key"])
            content = self.settings.get(key)
            return _Rows(one={"setting_value": content} if content is not None else None)
        if "UPDATE household_articles" in sql:
            assert params["household_id"] == "home-1"
            self.articles[params["article_id"]]["consumable"] = params["consumable"]
            return _Rows(rowcount=1)
        if "INSERT INTO household_article_settings" in sql:
            self.settings[(params["article_id"], params["setting_key"])] = params["setting_value"]
            return _Rows(rowcount=1)
        raise AssertionError("Unrecognized SQL: " + sql[:200])


def test_explicit_choice_persists_audit_and_preserves_other_articles():
    conn = _ReviewConn({
        "a": {"id": "a", "consumable": False},
        "b": {"id": "b", "consumable": False},
    })
    result = record_explicit_consumable_review(
        conn, household_id="home-1", article_id="a", actor_id="user-1",
        consumable=True, expected_state="false",
    )
    assert result["status"] == "reviewed"
    assert conn.articles["a"]["consumable"] == 1  # legacy PostgreSQL storage is integer
    assert conn.articles["b"]["consumable"] is False
    assert next(params for sql, params in conn.calls if "UPDATE household_articles" in sql)["consumable"] == 1
    origin = json.loads(conn.settings[("a", ORIGIN_KEY)])
    assert origin["kind"] == "explicit_user"
    assert origin["actor_id"] == "user-1"
    history = json.loads(conn.settings[("a", HISTORY_KEY)])
    assert len(history) == 1
    assert history[0]["old"] is False and history[0]["new"] is True
    result = record_explicit_consumable_review(
        conn, household_id="home-1", article_id="a", actor_id="user-1",
        consumable=True, expected_state="true",
    )
    assert result["status"] == "unchanged"
    assert len(json.loads(conn.settings[("a", HISTORY_KEY)])) == 1


def test_stale_state_fails_before_any_classification_or_setting_write():
    conn = _ReviewConn({"a": {"id": "a", "consumable": False}})
    with pytest.raises(ReviewConflict):
        record_explicit_consumable_review(
            conn, household_id="home-1", article_id="a", actor_id="user-1",
            consumable=True, expected_state="unknown",
        )
    assert not any("UPDATE household_articles" in sql for sql, _ in conn.calls)
    assert not conn.settings


def test_cross_household_article_rejected_without_fallback_by_name():
    conn = _ReviewConn({})
    with pytest.raises(ReviewNotFound):
        record_explicit_consumable_review(
            conn, household_id="home-1", article_id="foreign",
            actor_id="user-1", consumable=True, expected_state="false",
        )
    assert not any("UPDATE household_articles" in sql for sql, _ in conn.calls)


def test_invalid_preexisting_history_refuses_to_erase_evidence():
    conn = _ReviewConn(
        {"a": {"id": "a", "consumable": False}},
        {("a", HISTORY_KEY): "broken-json"},
    )
    with pytest.raises(ReviewConflict):
        record_explicit_consumable_review(
            conn, household_id="home-1", article_id="a", actor_id="user-1",
            consumable=True, expected_state="false",
        )
    assert conn.articles["a"]["consumable"] is False


def test_review_list_preserves_original_values_and_household_filter(monkeypatch):
    class PreviewConn:
        def __init__(self):
            self.statements = []
        def execute(self, statement, params):
            sql = str(statement)
            self.statements.append(sql)
            assert "ha.household_id = :household_id" in sql
            assert "hs.id IS NULL" in sql
            assert "ha.consumable = 0" in sql
            return _Rows(
                scalar=2,
                many=[
                    {"id": "a", "naam": "Melk", "consumable": False},
                    {"id": "b", "naam": "Onbekend", "consumable": None},
                ],
            )
    monkeypatch.setattr(
        "app.services.household_consumable_review.infer_food_consumable_from_seed",
        lambda name: True if name == "Melk" else None,
    )
    conn = PreviewConn()
    result = list_consumable_review_candidates(
        conn, household_id="home-1", limit=10, offset=0,
    )
    assert result["total"] == 2
    assert result["items"][0]["food_hint"] is True
    assert result["items"][1]["consumable"] is None
    assert len(conn.statements) == 2
    assert all(not sql.lstrip().startswith(("UPDATE", "DELETE", "INSERT"))
               for sql in conn.statements)


def test_proven_auto_origin_is_owned_and_cannot_override_explicit_user_choice():
    from app.services.household_consumable_review import record_classification_origin

    class RecordingConnection:
        def __init__(self):
            self.calls = []
        def execute(self, statement, params):
            self.calls.append((str(statement), params))

    conn = RecordingConnection()
    record_classification_origin(
        conn, household_id="home-1", article_id="article-1",
        kind="automatic_positive",
    )
    assert len(conn.calls) == 1
    sql, args = conn.calls[0]
    assert "ha.household_id = :household_id AND ha.id = :article_id" in sql
    assert "ON CONFLICT (household_article_id, setting_key) DO NOTHING" in sql
    assert args["household_id"] == "home-1"
    assert args["key"] == ORIGIN_KEY
    assert json.loads(args["value"])["kind"] == "automatic_positive"


def test_automatic_origin_requires_known_kind():
    from app.services.household_consumable_review import record_classification_origin
    with pytest.raises(ValueError):
        record_classification_origin(
            object(), household_id="home-1", article_id="article-1",
            kind="explicit_user",
        )
