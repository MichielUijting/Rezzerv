"""Bijna op photo projection: no writes, safe identity and group precedence."""
from __future__ import annotations

from app.services import almost_out_image_projection as projection


def _article(id_, product, url=''):
    return {'id': id_, 'household_id': 'target-household',
            'global_product_id': product, 'image_url': url}


def _item(id_, members=None, image=''):
    return {'household_article_id': id_,
            'member_article_ids': members or [], 'image_url': image}


def test_visible_group_prefers_own_then_other_matched_or_confirmed_member(monkeypatch):
    calls = []

    def resolver(_conn, _text, rows):
        calls.append({row['id'] for row in rows})
        # Existing resolver proves a directly confirmed synonym image for b,
        # but a photographed matched member c must take precedence.
        return {'a': '', 'b': 'https://img.example/synonym.jpg'}

    monkeypatch.setattr(projection, 'resolve_household_catalog_images', resolver)
    rows = [_article('a', 'product-a'),
            _article('b', 'product-b'),
            _article('c', 'product-c', 'https://img.example/member.jpg')]
    items = [_item('a', ['a', 'b', 'c'])]
    result = projection.fill_visible_almost_out_photos(object(), object(), rows, items)
    assert result[0]['image_url'] == 'https://img.example/member.jpg'
    assert calls == [{'a', 'b'}]


def test_own_catalog_photo_wins_and_unrelated_household_photo_never_used(monkeypatch):
    seen = []
    def resolver(_conn, _text, rows):
        seen.append({row['id'] for row in rows})
        return {'a': 'https://img.example/verified-synonym.jpg'}
    monkeypatch.setattr(projection, 'resolve_household_catalog_images', resolver)
    rows = [_article('a', 'product-a'),
            _article('b', 'product-b', 'https://img.example/confirmed-member.jpg'),
            _article('stranger', 'product-stranger', 'https://img.example/unrelated.jpg')]
    items = [_item('a', ['a', 'b']), _item('stranger', image='https://img.example/own.jpg')]
    result = projection.fill_visible_almost_out_photos(object(), object(), rows, items)
    assert result[0]['image_url'] == 'https://img.example/confirmed-member.jpg'
    assert result[1]['image_url'] == 'https://img.example/own.jpg'
    assert seen == [{'a'}]
    assert all('stranger' not in candidate for candidate in seen)


def test_direct_confirmed_synonym_fallback_without_stock_merge(monkeypatch):
    monkeypatch.setattr(projection, 'resolve_household_catalog_images',
                        lambda _conn, _text, rows: {
                            'a': 'https://img.example/verified-peer.jpg'})
    item = _item('a')
    projection.fill_visible_almost_out_photos(
        object(), object(), [_article('a', 'product-a')], [item])
    assert item['image_url'] == 'https://img.example/verified-peer.jpg'


def test_missing_and_conflicting_evidence_stays_without_photo(monkeypatch):
    monkeypatch.setattr(projection, 'resolve_household_catalog_images',
                        lambda _conn, _text, _rows: {})
    item = _item('a', ['a', 'unknown'])
    projection.fill_visible_almost_out_photos(
        object(), object(), [_article('a', 'product-a')], [item])
    assert not item['image_url']


def test_already_displayed_image_never_overwritten_or_queried(monkeypatch):
    def fail(*_args):
        raise AssertionError('No lookup needed for a photographed signal')
    monkeypatch.setattr(projection, 'resolve_household_catalog_images', fail)
    item = _item('a', image='https://img.example/current.jpg')
    projection.fill_visible_almost_out_photos(object(), object(), [], [item])
    assert item['image_url'].endswith('current.jpg')
