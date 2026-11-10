from sqlalchemy import create_engine, text
from app.services.synonym_auto_consume_identity import confirmed_household_synonym_pair


def _fixture():
    engine = create_engine('sqlite://')
    connection = engine.connect()
    for statement in (
        'CREATE TABLE global_products (id TEXT PRIMARY KEY, status TEXT)',
        'CREATE TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, global_product_id TEXT, status TEXT)',
        'CREATE TABLE article_synonym_links (left_product_id TEXT, right_product_id TEXT)',
        "INSERT INTO global_products VALUES ('A','active'),('B','active'),('C','active')",
        "INSERT INTO household_articles VALUES ('a','h1','A','active'),('b','h1','B','active'),('b2','h2','B','active')",
        "INSERT INTO article_synonym_links VALUES ('A','B')",
    ):
        connection.execute(text(statement))
    return connection


def test_confirmed_direct_pair_is_household_scoped():
    conn = _fixture()
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a', 'b')
    assert confirmed_household_synonym_pair(conn, 'h2', 'b2') == ('b2',)
    assert confirmed_household_synonym_pair(conn, 'h2', 'a') == ('a',)


def test_absent_link_keeps_original_identity():
    conn = _fixture()
    conn.execute(text('DELETE FROM article_synonym_links'))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)


def test_no_transitive_group_or_ambiguous_star():
    conn = _fixture()
    conn.execute(text("INSERT INTO article_synonym_links VALUES ('B','C')"))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
    assert confirmed_household_synonym_pair(conn, 'h1', 'b') == ('b',)


def test_duplicate_household_representation_fails_closed():
    conn = _fixture()
    conn.execute(text("INSERT INTO household_articles VALUES ('a2','h1','A','active')"))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)


def test_inactive_or_unlinked_catalog_does_not_guess_from_name():
    conn = _fixture()
    conn.execute(text("UPDATE global_products SET status='inactive' WHERE id='B'"))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
    conn.execute(text("UPDATE global_products SET status='active' WHERE id='B'"))
    conn.execute(text("UPDATE household_articles SET global_product_id=NULL WHERE id='a'"))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
