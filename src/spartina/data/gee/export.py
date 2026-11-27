"""Asynchronous export-task interfaces (M0 contracts + v1 landing helpers).

No network happens at import. The v1 factory adds provenance fields to
:class:`ExportRequest` (fixed grid, exact source scenes, science stream)
and local-file landing with mandatory SHA-256 verification; both remain
backward compatible with M0 callers.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExportRequest:
    """Description of one batched export job for one tile/time window."""

    request_id: str
    sensor_name: str
    tile_id: str
    start_date: str
    end_date: str
    destination_uri: str
    bands: tuple[str, ...]
    crs_epsg: int
    resolution_m: float
    #: GridSpec.to_dict() output — the exact fixed grid of the export.
    grid_spec: dict[str, object] | None = None
    #: Exact source scene IDs used (Issue #6 provenance requirement).
    source_scene_ids: tuple[str, ...] = ()
    #: "landsat_30m" or "sentinel_10m" science stream.
    science_stream: str | None = None


@dataclass(frozen=True)
class ExportTask:
    """Handle returned after an export has been enqueued."""

    task_id: str
    request_id: str
    state: str  # e.g. "MOCK_ENQUEUED" in M0; GEE states in M1+
    messages: tuple[str, ...] = field(default_factory=tuple)


class Exporter(Protocol):
    """Interface for export backends."""

    def submit(self, request: ExportRequest) -> ExportTask:
        """Enqueue (never synchronously materialize) an export."""
        ...


class NullExporter:
    """Offline exporter used by unit tests: records calls, touches nothing."""

    def __init__(self) -> None:
        self.submitted: list[ExportRequest] = []

    def submit(self, request: ExportRequest) -> ExportTask:
        """Record the request and return a mock task handle."""
        self.submitted.append(request)
        return ExportTask(
            task_id=f"mock-{request.request_id}",
            request_id=request.request_id,
            state="MOCK_ENQUEUED",
            messages=("No network or filesystem export performed.",),
        )


def sha256_bytes(data: bytes) -> str:
    """SHA-256 hex digest of in-memory export bytes."""
    return hashlib.sha256(data).hexdigest()


def land_bytes(
    destination: str | Path, data: bytes,
    *, expected_sha256: str | None = None,
) -> dict[str, str | int]:
    """Write export bytes locally and return checksum provenance.

    Raises ``ValueError`` if ``expected_sha256`` is supplied and does not
    match the landed bytes. Files are written to a temp sibling and
    renamed so a crashed attempt can never leave a half-written asset
    masquerading as complete.
    """
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    checksum = sha256_bytes(data)
    if expected_sha256 is not None and checksum != expected_sha256:
        raise ValueError(
            f"checksum mismatch for {path}: got {checksum}, "
            f"expected {expected_sha256}")
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return {"local_uri": str(path), "sha256": checksum,
            "size_bytes": len(data)}


__all__ = [
    "ExportRequest",
    "ExportTask",
    "Exporter",
    "NullExporter",
    "land_bytes",
    "sha256_bytes",
]
