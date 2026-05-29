from __future__ import annotations

"""Python startup customisation for Rezzerv.

R9-36N4:
This file must not import patch modules or mutate runtime behaviour.
Python automatically imports sitecustomize when it is present on sys.path, so any
side effect here runs before normal application startup and is hard to reason
about. Keep this module intentionally empty.
"""
