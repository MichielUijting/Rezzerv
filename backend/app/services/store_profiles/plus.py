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

PLUS_PROFILE = StoreProfile(
    key='plus',
    display_name='Plus',
    store_patterns=(r'\\bplus\\b',),
    loyalty_patterns=(r'pluspunt', r'pluspunten', r'zegel'),
    discount_patterns=(r'actie', r'korting', r'voordeel'),
)
