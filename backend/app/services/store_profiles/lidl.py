from app.services.store_profiles.base import StoreProfile

LIDL_PROFILE = StoreProfile(
    key='lidl',
    display_name='Lidl',
    store_patterns=(r'\\blidl\\b',),
    loyalty_patterns=(r'lidl plus',),
    discount_patterns=(r'korting', r'bespaard', r'voordeel'),
)
