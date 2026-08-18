from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.api.article_detail_admin_routes import _install_admin_guard


class PatchPayload(BaseModel):
    custom_name: str | None = None


def require_household_admin_context(authorization: str | None):
    token = str(authorization or '').strip()
    if token != 'Bearer owner':
        raise HTTPException(status_code=403, detail='Alleen eigenaar of admin')
    return {'active_household_id': 'household-a', 'display_role': 'admin'}


def _canonical_patch(household_article_id: str, payload: PatchPayload, authorization: str | None = Header(None)):
    return {
        'household_article_id': household_article_id,
        'custom_name': payload.custom_name,
        'authorization': authorization,
    }


# De productiezoeker selecteert bewust alleen de canonieke app.main-route.
_canonical_patch.__module__ = 'app.main'


def _app_with_canonical_patch() -> FastAPI:
    app = FastAPI()
    app.patch('/api/household-articles/{household_article_id}')(_canonical_patch)
    return app


def test_guard_reuses_single_canonical_route_and_blocks_member() -> None:
    app = _app_with_canonical_patch()
    main_module = SimpleNamespace(app=app)

    _install_admin_guard(main_module, '/api/household-articles/{household_article_id}', 'PATCH')

    matching = [
        route
        for route in app.routes
        if getattr(route, 'path', None) == '/api/household-articles/{household_article_id}'
        and 'PATCH' in set(getattr(route, 'methods', set()) or set())
    ]
    assert len(matching) == 1
    route = matching[0]
    assert getattr(route.dependant.call, '_rezzerv_article_detail_admin_guard', False) is True

    try:
        route.dependant.call(
            household_article_id='article-a',
            payload=PatchPayload(custom_name='Lid mag niet schrijven'),
            authorization='Bearer member',
        )
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError('Lid bereikte de canonieke PATCH-mutatie')

    result = route.dependant.call(
        household_article_id='article-a',
        payload=PatchPayload(custom_name='Eigen naam'),
        authorization='Bearer owner',
    )
    assert result['household_article_id'] == 'article-a'
    assert result['custom_name'] == 'Eigen naam'


def test_guard_installation_is_idempotent() -> None:
    app = _app_with_canonical_patch()
    main_module = SimpleNamespace(app=app)

    _install_admin_guard(main_module, '/api/household-articles/{household_article_id}', 'PATCH')
    route = next(
        route
        for route in app.routes
        if getattr(route, 'path', None) == '/api/household-articles/{household_article_id}'
        and 'PATCH' in set(getattr(route, 'methods', set()) or set())
    )
    first_guard = route.dependant.call
    _install_admin_guard(main_module, '/api/household-articles/{household_article_id}', 'PATCH')
    assert route.dependant.call is first_guard


if __name__ == '__main__':
    test_guard_reuses_single_canonical_route_and_blocks_member()
    test_guard_installation_is_idempotent()
    print('ARTICLE_DETAIL_CANONICAL_ROUTE_GUARD_GREEN')
