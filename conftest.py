"""Root conftest.

Its presence makes pytest prepend the repository root to ``sys.path``, so the
``src`` package resolves whether tests run via ``pytest`` or ``python -m pytest``.
"""
