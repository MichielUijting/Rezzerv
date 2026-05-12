from app.services.store_profiles.base import StoreProfile

JUMBO_PROFILE = StoreProfile(
    key='jumbo',
    display_name='Jumbo',
    store_patterns=('jumbo',),
    loyalty_patterns=('koopzegel', 'zegel'),
    discount_patterns=('actie', 'korting', 'voordeel'),
)
