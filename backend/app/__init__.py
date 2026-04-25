# Activate receipt parser patch
try:
    import app.services.receipt_line_window_parser_patch  # noqa: F401
except Exception:
    pass
