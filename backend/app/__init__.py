"""Rezzerv application package bootstrap.

Keep this file lightweight. It patches presentation-only fallbacks before
app.main imports service symbols directly from app.services.*.
"""

try:
    from app.services import receipt_service as _receipt_service

    _original_serialize_receipt_row = getattr(_receipt_service, "serialize_receipt_row", None)

    def _line_display_name(line):
        if not isinstance(line, dict):
            return None
        return (
            line.get("article_name")
            or line.get("matched_article_name")
            or line.get("corrected_raw_label")
            or line.get("raw_label")
            or line.get("normalized_label")
            or line.get("label")
            or line.get("text")
        )

    def _apply_receipt_line_article_name_fallback(value):
        if isinstance(value, dict):
            for key in ("lines", "accepted_lines", "items", "receipt_lines"):
                lines = value.get(key)
                if isinstance(lines, list):
                    for line in lines:
                        if isinstance(line, dict):
                            fallback = _line_display_name(line)
                            if fallback:
                                line.setdefault("article_name", fallback)
                                line.setdefault("text", fallback)
                                line.setdefault("raw_label", fallback)
                                line.setdefault("normalized_label", line.get("normalized_label") or fallback)
            return value
        if isinstance(value, list):
            for item in value:
                _apply_receipt_line_article_name_fallback(item)
        return value

    if callable(_original_serialize_receipt_row):
        def serialize_receipt_row(*args, **kwargs):
            return _apply_receipt_line_article_name_fallback(_original_serialize_receipt_row(*args, **kwargs))

        _receipt_service.serialize_receipt_row = serialize_receipt_row
except Exception:
    # Presentation fallback must never block API startup.
    pass
