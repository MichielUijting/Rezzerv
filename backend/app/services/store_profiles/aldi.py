from app.services.store_profiles.base import StoreProfile

ALDI_PROFILE = StoreProfile(
    key='aldi',
    display_name='ALDI',
    store_patterns=(r'\\baldi\\b',),
)
