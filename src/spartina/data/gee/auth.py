"""GEE authentication detection (credentials are never stored or printed).

M0 contract:
    * No credentials live in the repository.
    * Code detects whether credentials are available; if not, callers and
      integration tests skip GEE operations.
    * We do not invoke browser-based interactive login from automated code.
"""

from __future__ import annotations

import os
from pathlib import Path

# Standard Earth Engine / Google auth environment variables (names only).
_SERVICE_ACCOUNT_VARS: tuple[str, ...] = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "EE_SERVICE_ACCOUNT_JSON",
)
_USER_CREDENTIAL_CANDIDATES: tuple[str, ...] = (
    "~/.config/earthengine/credentials",
    "~/.config/earthengine/token.json",
)


def credentials_available() -> bool:
    """Return True if *some* local GEE credential appears to exist.

    Checks only file existence / variable presence — never reads or logs
    credential contents.
    """
    for var in _SERVICE_ACCOUNT_VARS:
        value = os.environ.get(var)
        if value:
            if var == "GOOGLE_APPLICATION_CREDENTIALS" and not Path(value).expanduser().is_file():
                # Variable points at a missing file: treat as unavailable.
                continue
            return True
    return any(Path(path).expanduser().is_file() for path in _USER_CREDENTIAL_CANDIDATES)


def initialize() -> None:
    """Initialize the Earth Engine API if credentials are available.

    Raises:
        RuntimeError: if credentials are missing or the (optional)
            ``earthengine-api`` package is not installed. The error message
            tells the user how to authenticate; the code never performs an
            interactive login itself.
    """
    if not credentials_available():
        raise RuntimeError(
            "No Earth Engine credentials found. Authenticate interactively "
            "outside automated code (`earthengine authenticate` in your own "
            "shell) or provide a service-account file via "
            "GOOGLE_APPLICATION_CREDENTIALS. Never commit credentials."
        )
    try:
        import ee  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("earthengine-api is not installed (optional 'gee' extra, M1+).") from exc
    ee.Initialize()  # pragma: no cover - exercised only with real credentials


__all__ = ["credentials_available", "initialize"]
