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

JUMBO_PROFILE = StoreProfile(
    key='jumbo',
    display_name='Jumbo',
    store_patterns=('jumbo',),
    loyalty_patterns=('koopzegel', 'zegel'),
    discount_patterns=('actie', 'korting', 'voordeel'),
)
