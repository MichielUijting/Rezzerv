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

AH_PROFILE = StoreProfile(
    key='ah',
    display_name='Albert Heijn',
    store_patterns=(r'albert\\s*heijn', r'\\bah\\b'),
    loyalty_patterns=(r'bonuskaart', r'koopzegels?', r'es?paarzegels?', r'pluspunten?'),
    discount_patterns=(r'bonus', r'bbox', r'korting', r'voordeel'),
)
