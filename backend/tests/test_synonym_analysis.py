"""Read-only synonym analytics never infer a substitute or transitive link."""
import unittest

from app.services.article_synonym_service import build_synonym_analysis


def item(id, name, store, brick='milk'):
    return {
        'id': id, 'name': name, 'brand': '', 'variant': '',
        'size_value': '1', 'size_unit': 'l', 'image_url': '',
        'retailer_code': store, 'store_name': store.upper() if store else 'Niet vastgelegd',
        'brick_code': brick,
    }


class AnalysisTest(unittest.TestCase):
    def test_direct_unique_stores_and_pending_are_independent(self):
        products = [item('a', 'Halfvolle melk', 'ah'), item('b', 'Halfvolle melk', 'jumbo'),
                    item('c', 'Halfvolle melk', 'lidl'), item('d', 'Halfvolle melk', 'plus')]
        suggested = [{'left': products[0], 'right': products[3], 'score': .91}]
        analysis = build_synonym_analysis(
            products, {('a', 'b'), ('a', 'c'), ('b', 'c')}, suggested,
            {'a': 'Melk', 'b': 'Melk', 'c': 'Melk', 'd': 'Melk'})
        rows = {row['id']: row for row in analysis['items']}
        self.assertEqual(analysis['summary']['confirmed_pairs'], 3)
        self.assertEqual(analysis['summary']['synonym_buckets'], {'0': 1, '1': 0, '2': 3, '3+': 0})
        self.assertEqual(rows['a']['synonym_count'], 2)
        self.assertEqual(rows['d']['synonym_count'], 0)
        self.assertEqual(analysis['summary']['candidate_pairs'], 1)
        self.assertEqual(rows['a']['linked_stores'], ['Jumbo', 'Lidl'])
        self.assertEqual(rows['a']['status'], 'review')
        self.assertEqual(rows['d']['status'], 'review')
        self.assertEqual(rows['b']['status'], 'linked')
        self.assertEqual(rows['d']['linked_stores'], [])
        self.assertEqual(sum(g['articles'] for g in analysis['groups']), 4)

    def test_no_store_does_not_count_as_missing_supermarket_assortment(self):
        products = [item('a', 'Amandelmelk', ''), item('b', 'Amandelmelk', 'aldi')]
        analysis = build_synonym_analysis(products, {('a', 'b')}, [])
        self.assertEqual(analysis['summary']['confirmed_pairs'], 0)
        self.assertEqual(analysis['summary']['insufficient_articles'], 1)
        self.assertEqual(analysis['summary']['synonym_buckets'], {'0': 2, '1': 0, '2': 0, '3+': 0})
        self.assertEqual(analysis['summary']['no_candidate_articles'], 1)
        self.assertEqual(analysis['items'][0]['store'], 'Winkel onbekend')

    def test_unclassified_is_not_auto_assigned_equivalence(self):
        products = [item('a', 'Melk', 'ah', ''), item('b', 'Melk', 'jumbo', '')]
        analysis = build_synonym_analysis(products, set(), [], {})
        self.assertEqual({p['group_label'] for p in analysis['items']}, {'Niet geclassificeerd'})
        self.assertEqual(analysis['summary']['confirmed_pairs'], 0)
        self.assertEqual(analysis['summary']['candidate_pairs'], 0)


if __name__ == '__main__':
    unittest.main()
