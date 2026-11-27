"""Tide / inundation metadata — PROXY interfaces only (Issue #6, B5).

Spartina mapping on tidal flats is tide-state sensitive, but this
factory must **not** invent tidal observations. No astronomical tide
model output, gauge interpolation or inundation map is presented as a
measurement. Only explicit proxy placeholders are allowed until a real
tide-gauge / validated tide-model feed is integrated:

* ``method == "PROXY"`` is mandatory for every record;
* the proxy basis must be named (e.g. scene acquisition metadata,
  rough shoreline fraction, external model identifier);
* ``gauge_observed`` is always ``False`` here and confidence stays
  ``UNKNOWN``.

Real tide gauge integration is a later, separately evidenced task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PROXY_METHOD: Final[str] = "PROXY"
UNKNOWN: Final[str] = "UNKNOWN"


@dataclass(frozen=True)
class TideProxyRecord:
    """Proxy tide/inundation context for one scene (never a measurement)."""

    scene_id: str
    acquisition_utc: str | None
    proxy_basis: str
    proxy_value: float | None
    notes: str = ""
    method: str = PROXY_METHOD
    gauge_observed: bool = False
    confidence: str = UNKNOWN

    def __post_init__(self) -> None:
        if self.method != PROXY_METHOD:
            raise ValueError(
                "only PROXY tide/inundation metadata is permitted at "
                "Data Factory v1; real gauge feeds are not integrated")
        if self.gauge_observed:
            raise ValueError(
                "gauge_observed=True is forbidden until a real gauge "
                "feed is integrated and documented")
        if not self.proxy_basis:
            raise ValueError("proxy_basis must name what the proxy uses")

    def to_record(self) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "acquisition_utc": self.acquisition_utc,
            "method": self.method,
            "gauge_observed": self.gauge_observed,
            "confidence": self.confidence,
            "proxy_basis": self.proxy_basis,
            "proxy_value": self.proxy_value,
            "notes": (
                self.notes or "PROXY ONLY — not a tide-gauge observation; "
                "do not interpret as measured water level/inundation"),
        }


def no_tide_metadata(scene_id: str,
                     acquisition_utc: str | None = None) -> TideProxyRecord:
    """Explicit 'no tide context' record (preferred over silent omission)."""
    return TideProxyRecord(
        scene_id=scene_id, acquisition_utc=acquisition_utc,
        proxy_basis="none_available", proxy_value=None,
        notes="no tide proxy or gauge data attached at factory time")


__all__ = ["PROXY_METHOD", "TideProxyRecord", "UNKNOWN", "no_tide_metadata"]
