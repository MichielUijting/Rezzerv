"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from app.services.store_profiles.base import StoreProfile

LIDL_PROFILE = StoreProfile(
    key='lidl',
    display_name='Lidl',
    store_patterns=(r'\\blidl\\b',),
    loyalty_patterns=(r'lidl plus',),
    discount_patterns=(r'korting', r'bespaard', r'voordeel'),
)
