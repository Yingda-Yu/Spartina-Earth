"""Download batch-exported files from Google Drive after an EE task.

``ee.batch.Export.image.toDrive`` produces a real, pollable Earth Engine
task whose output lands in the authenticated user's Google Drive (the
official ``earthengine authenticate`` OAuth flow already requests the
Drive scope, alongside EE and Cloud Storage). This module turns the
finished Drive file back into local bytes for checksum/manifest landing.

Everything is lazy: no Drive client is built until a real export smoke is
explicitly run. Credentials are never read from or written to this
repository.
"""

from __future__ import annotations

import io
from typing import Any, Final

#: OAuth scope set granted by `earthengine authenticate` (ee.oauth.SCOPES).
DRIVE_SCOPE: Final[str] = "https://www.googleapis.com/auth/drive"


class DriveDownloadError(RuntimeError):
    """The finished export could not be retrieved from Google Drive."""


def _credentials() -> Any:
    try:
        import ee
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise DriveDownloadError(
            "google-api client / oauth libraries missing; real Drive "
            "retrieval is part of the 'gee' install (earthengine-api)."
        ) from exc
    # get_credentials_arguments() returns refresh_token/client/scopes but
    # never a live access token; google's Credentials constructor still
    # requires the (possibly-None) positional "token", which refresh()
    # below exchanges for. This path was exercised for the first time by
    # the M1.6c real Sentinel-2 byte export.
    args = dict(ee.oauth.get_credentials_arguments())
    args.pop("token", None)
    # google-auth ships py.typed but Credentials.__init__ and the base
    # refresh() remain unannotated (verified 2.59.0), so --strict needs
    # targeted no-untyped-call ignores at this third-party boundary.
    creds = Credentials(token=None, **args)  # type: ignore[no-untyped-call]
    creds.refresh(Request())  # type: ignore[no-untyped-call]
    return creds


def _service() -> Any:
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DriveDownloadError("google-api-python-client is unavailable") from exc
    return build("drive", "v3", credentials=_credentials(),
                 cache_discovery=False)


def find_latest_file(name_prefix: str) -> tuple[str, str]:
    """Return ``(file_id, name)`` of the newest non-trashed match.

    Raises if zero or multiple ambiguity can't be resolved: the newest
    modified file wins, because re-runs reuse descriptive name prefixes.
    """
    service = _service()
    query = f"name contains '{name_prefix}' and trashed = false"
    response = service.files().list(
        q=query,
        fields="files(id,name,modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=10,
    ).execute()
    files = list(response.get("files", []))
    if not files:
        raise DriveDownloadError(
            f"no Drive file matching {name_prefix!r}; the export task may "
            "not have completed or the OAuth client lacks Drive access")
    first = files[0]
    return str(first["id"]), str(first["name"])


def download_latest(name_prefix: str) -> tuple[str, bytes]:
    """Download the newest Drive file matching ``name_prefix``."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DriveDownloadError("google-api-python-client is unavailable") from exc
    service = _service()
    file_id, name = find_latest_file(name_prefix)
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _progress, done = downloader.next_chunk()
    return name, buffer.getvalue()


__all__ = ["DRIVE_SCOPE", "DriveDownloadError", "download_latest",
           "find_latest_file"]
