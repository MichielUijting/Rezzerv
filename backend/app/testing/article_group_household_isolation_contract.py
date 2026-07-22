"""Contracttest voor artikelgroep-isolatie tussen huishoudens A en B.

Run vanuit repository root met:
    PYTHONPATH=backend python -m app.testing.article_group_household_isolation_contract
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services import article_group_secure_store as secure_store
from app.services import article_group_store as legacy_store


def _expect_failure(result: dict, expected_error: str) -> None:
    assert result.get("ok") is False, result
    assert result.get("error") == expected_error, result


def run_contract() -> None:
    original_engine = legacy_store.engine

    with tempfile.TemporaryDirectory(prefix="rezzerv-article-group-isolation-") as tmp:
        database_path = Path(tmp) / "contract.sqlite"
        test_engine = create_engine(
            f"sqlite:///{database_path}",
            connect_args={"check_same_thread": False},
        )
        legacy_store.engine = test_engine

        try:
            with test_engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE household_articles (
                            id TEXT PRIMARY KEY,
                            household_id TEXT NOT NULL,
                            custom_name TEXT,
                            article_group_id TEXT
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO household_articles (
                            id,
                            household_id,
                            custom_name,
                            article_group_id
                        ) VALUES
                            ('article-a', 'household-a', 'Artikel A', NULL),
                            ('article-b', 'household-b', 'Artikel B', NULL)
                        """
                    )
                )

            group_a = secure_store.create_article_group("household-a", "Groep A")
            group_b = secure_store.create_article_group("household-b", "Groep B")
            assert group_a.get("ok") is True, group_a
            assert group_b.get("ok") is True, group_b

            group_a_id = str(group_a["item"]["id"])
            group_b_id = str(group_b["item"]["id"])

            own_update = secure_store.update_article_group(
                group_id=group_a_id,
                household_id="household-a",
                name="Groep A gewijzigd",
            )
            assert own_update.get("ok") is True, own_update

            _expect_failure(
                secure_store.update_article_group(
                    group_id=group_b_id,
                    household_id="household-a",
                    name="Ongeoorloofd gewijzigd",
                ),
                "Artikelgroep niet gevonden",
            )
            _expect_failure(
                secure_store.delete_article_group(
                    group_id=group_b_id,
                    household_id="household-a",
                ),
                "Artikelgroep niet gevonden",
            )
            _expect_failure(
                secure_store.assign_household_article_group(
                    article_id="article-b",
                    article_group_id=group_a_id,
                    household_id="household-a",
                ),
                "Huishoudelijk artikel niet gevonden",
            )
            _expect_failure(
                secure_store.assign_household_article_group(
                    article_id="article-a",
                    article_group_id=group_b_id,
                    household_id="household-a",
                ),
                "Artikelgroep niet gevonden",
            )

            own_assignment = secure_store.assign_household_article_group(
                article_id="article-a",
                article_group_id=group_a_id,
                household_id="household-a",
            )
            assert own_assignment.get("ok") is True, own_assignment

            with test_engine.begin() as conn:
                article_a = conn.execute(
                    text(
                        """
                        SELECT household_id, article_group_id
                        FROM household_articles
                        WHERE id = 'article-a'
                        """
                    )
                ).mappings().one()
                article_b = conn.execute(
                    text(
                        """
                        SELECT household_id, article_group_id
                        FROM household_articles
                        WHERE id = 'article-b'
                        """
                    )
                ).mappings().one()
                stored_group_b = conn.execute(
                    text(
                        """
                        SELECT household_id, name
                        FROM article_groups
                        WHERE id = :id
                        """
                    ),
                    {"id": group_b_id},
                ).mappings().one()

            assert article_a["household_id"] == "household-a"
            assert article_a["article_group_id"] == group_a_id
            assert article_b["household_id"] == "household-b"
            assert article_b["article_group_id"] is None
            assert stored_group_b["household_id"] == "household-b"
            assert stored_group_b["name"] == "Groep B"

            print("ARTICLE_GROUP_HOUSEHOLD_ISOLATION_CONTRACT_GREEN")
        finally:
            legacy_store.engine = original_engine
            test_engine.dispose()


if __name__ == "__main__":
    run_contract()
