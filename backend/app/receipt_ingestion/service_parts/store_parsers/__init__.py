"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

"""Store-specific parser modules.

R9-38A2-ARCH starts splitting the large store_specific_parsers module into
smaller store-focused parser modules. This package must remain free of receipt
status decisions; functional status stays in the SSOT status service.
"""
