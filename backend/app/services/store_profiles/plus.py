from app.services.store_profiles.base import StoreProfile

PLUS_PROFILE = StoreProfile(
    key='plus',
    display_name='Plus',
    store_patterns=(r'\\bplus\\b',),
    loyalty_patterns=(r'pluspunt', r'pluspunten', r'zegel'),
    discount_patterns=(r'actie', r'korting', r'voordeel'),
)
