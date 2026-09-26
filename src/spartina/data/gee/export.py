"""Asynchronous export-task interfaces (M0 contracts, no real exports)."""

from __future__ import annotations

from dataclasses import dataclass, field
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


__all__ = ["ExportRequest", "ExportTask", "Exporter", "NullExporter"]
