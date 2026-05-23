from app.services.store_profiles.base import StoreProfile

AH_PROFILE = StoreProfile(
    key='ah',
    display_name='Albert Heijn',
    store_patterns=(r'albert\\s*heijn', r'\\bah\\b'),
    loyalty_patterns=(r'bonuskaart', r'koopzegels?', r'es?paarzegels?', r'pluspunten?'),
    discount_patterns=(r'bonus', r'bbox', r'korting', r'voordeel'),
)
