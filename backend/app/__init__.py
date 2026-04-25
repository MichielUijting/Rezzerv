# Activate receipt status sync
try:
    from app.services.receipt_status_sync import install_receipt_status_sync
    install_receipt_status_sync()
except Exception:
    pass
