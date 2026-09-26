"""Real GEE integration smoke test.

Auto-skips unless genuine credentials are present. Never runs under the
default M0 test selection in CI; execute manually in M1+ with:

    pytest -m gee_integration

Even then, this must stay a tiny smoke query — never a nationwide export.
"""

from __future__ import annotations

import pytest

from spartina.data.gee import auth

pytestmark = [
    pytest.mark.gee_integration,
    pytest.mark.skipif(
        not auth.credentials_available(),
        reason="GEE credentials not configured; integration test skipped.",
    ),
]


def test_ee_initialize_smoke() -> None:
    """Initialize and perform one tiny catalog-level operation."""
    auth.initialize()  # pragma: no cover - requires real credentials
    import ee  # type: ignore[import-not-found]  # pragma: no cover

    result = ee.Number(1).getInfo()  # pragma: no cover
    assert result == 1  # pragma: no cover
