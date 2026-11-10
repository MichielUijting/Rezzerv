from app.services.synonym_auto_consume_identity import confirmed_household_synonym_pair


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _FakeConnection:
    def __init__(self):
        self.products = {'A': 'active', 'B': 'active', 'C': 'active'}
        self.articles = [
            {'id': 'a', 'household_id': 'h1', 'global_product_id': 'A', 'status': 'active'},
            {'id': 'b', 'household_id': 'h1', 'global_product_id': 'B', 'status': 'active'},
            {'id': 'b2', 'household_id': 'h2', 'global_product_id': 'B', 'status': 'active'},
        ]
        self.links = [('A', 'B')]

    def execute(self, statement, params):
        sql = str(statement)
        if 'SELECT ha.global_product_id' in sql:
            return _Result([{'global_product_id': a['global_product_id']} for a in self.articles
                if a['id'] == params['article_id'] and a['household_id'] == params['household_id']
                and a['status'] == 'active' and self.products.get(a['global_product_id']) == 'active'])
        if 'CASE WHEN left_product_id' in sql:
            product = params['catalog_id']
            return _Result([{'partner': right if left == product else left} for left, right in self.links
                if product in (left, right)])
        if 'SELECT 1 FROM article_synonym_links' in sql:
            return _Result([{'exists': 1} for pair in self.links if params['partner'] in pair])
        if 'SELECT ha.id, ha.global_product_id' in sql:
            return _Result([{'id': a['id'], 'global_product_id': a['global_product_id']} for a in self.articles
                if a['household_id'] == params['household_id'] and a['status'] == 'active'
                and a['global_product_id'] in (params['catalog_id'], params['partner'])
                and self.products.get(a['global_product_id']) == 'active'])
        raise AssertionError(f'Unexpected database access: {sql[:100]}')


def test_confirmed_direct_pair_is_household_scoped():
    conn = _FakeConnection()
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a', 'b')
    assert confirmed_household_synonym_pair(conn, 'h2', 'b2') == ('b2',)
    assert confirmed_household_synonym_pair(conn, 'h2', 'a') == ('a',)


def test_absent_link_keeps_original_identity():
    conn = _FakeConnection()
    conn.links.clear()
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)


def test_no_transitive_group_or_ambiguous_star():
    conn = _FakeConnection()
    conn.links.append(('B', 'C'))
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
    assert confirmed_household_synonym_pair(conn, 'h1', 'b') == ('b',)


def test_duplicate_household_representation_fails_closed():
    conn = _FakeConnection()
    conn.articles.append({'id': 'a2', 'household_id': 'h1', 'global_product_id': 'A', 'status': 'active'})
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)


def test_inactive_or_unlinked_catalog_does_not_guess_from_name():
    conn = _FakeConnection()
    conn.products['B'] = 'inactive'
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
    conn.products['B'] = 'active'
    conn.articles[0]['global_product_id'] = None
    assert confirmed_household_synonym_pair(conn, 'h1', 'a') == ('a',)
