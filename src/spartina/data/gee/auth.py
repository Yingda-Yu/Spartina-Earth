"""GEE authentication detection (credentials are never stored or printed).

Contract:
    * No credentials live in the repository.
    * Code detects whether credentials are available; if not, callers and
      integration tests skip GEE operations.
    * We do not invoke browser-based interactive login from automated code.
    * The Google Cloud project is read exclusively from the
      ``SPARTINA_GEE_PROJECT`` environment variable; it is never hard-coded.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

# Standard Earth Engine / Google auth environment variables (names only).
_SERVICE_ACCOUNT_VARS: tuple[str, ...] = (
    "GOOGLE_APPLICATION_CREDENTIALS",
    "EE_SERVICE_ACCOUNT_JSON",
)
_USER_CREDENTIAL_CANDIDATES: tuple[str, ...] = (
    "~/.config/earthengine/credentials",
    "~/.config/earthengine/token.json",
)

# The Google Cloud project that has Earth Engine enabled. Operators export
# SPARTINA_GEE_PROJECT in their own shell; source files never embed it.
PROJECT_ENV_VAR: Final[str] = "SPARTINA_GEE_PROJECT"


def credentials_available() -> bool:
    """Return True if *some* local GEE credential appears to exist.

    Checks only file existence / variable presence -- never reads or logs
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


def configured_project() -> str | None:
    """Return the GCP project id configured for Earth Engine, if any."""
    value = os.environ.get(PROJECT_ENV_VAR, "").strip()
    return value or None


def initialize() -> None:
    """Initialize the Earth Engine API if credentials are available.

    The Google Cloud project is taken exclusively from
    ``SPARTINA_GEE_PROJECT`` and passed to ``ee.Initialize``. Raises if
    credentials are missing, the project env var is unset, or the
    (optional) ``earthengine-api`` package is not installed. The code
    never performs an interactive login itself.
    """
    if not credentials_available():
        raise RuntimeError(
            "No Earth Engine credentials found. Authenticate interactively "
            "outside automated code (`earthengine authenticate` in your own "
            "shell) or provide a service-account file via "
            "GOOGLE_APPLICATION_CREDENTIALS. Never commit credentials."
        )
    project = configured_project()
    if project is None:
        raise RuntimeError(
            f"Earth Engine requires a Google Cloud project with the EE API "
            f"enabled; export {PROJECT_ENV_VAR}=<your-project-id>. "
            f"It is never hard-coded in source."
        )
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError(
            "earthengine-api is not installed (optional 'gee' extra, M1+)."
        ) from exc
    # pragma: no cover - exercised only with real credentials
    ee.Initialize(project=project)


__all__ = [
    "PROJECT_ENV_VAR",
    "configured_project",
    "credentials_available",
    "initialize",
]
