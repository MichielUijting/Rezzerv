from app.services.store_profiles.base import StoreProfile

JUMBO_PROFILE = StoreProfile(
    key='jumbo',
    display_name='Jumbo',
    store_patterns=(r'\bjumbo\b',),
    loyalty_patterns=(r'koopzegel', r'zegel'),
    receipt_line_loyalty_patterns=(r'koopzegel.*-?\d{1,6}[\.,]\d{2}',),
    discount_patterns=(r'actie', r'korting', r'voordeel'),
)
