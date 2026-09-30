"""GoldSet isolation check (Issue #11 §6).

Final GOLD evaluation sites must never touch a training / validation /
threshold-fitting / weak-label-tuning / hyperparameter-search spatial
unit, including a buffer. This module is the freeze-time hard gate.

Following :mod:`spartina.evaluation.splits`, the v0 geometry backend is
intentionally dependency-free: each unit is an axis-aligned envelope in
one projected CRS (metres). Polygon envelopes are conservative (their
bounding boxes), so the check can only over-flag leakage, never miss it.
A later shapely backend may tighten false positives behind the same
interface.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Bounds = tuple[float, float, float, float]


@dataclass(frozen=True)
class Envelope:
    """An axis-aligned spatial envelope in a projected CRS (metres)."""

    site_id: str
    bounds: Bounds  # (west, south, east, north)
    crs_epsg: int

    def __post_init__(self) -> None:
        west, south, east, north = self.bounds
        if not (east > west and north > south):
            raise ValueError(f"invalid bounds for {self.site_id!r}: {self.bounds}")
        if not isinstance(self.crs_epsg, int):
            raise ValueError("crs_epsg must be an integer EPSG code")

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Envelope:
        """Build from a manifest row: site_id/id, bounds, crs_epsg."""
        site_id = record.get("site_id") or record.get("id")
        raw_bounds = record.get("bounds")
        crs = record.get("crs_epsg")
        if not isinstance(site_id, str) or not isinstance(crs, int):
            raise ValueError(f"malformed envelope record: {record!r}")
        if (not isinstance(raw_bounds, Sequence) or isinstance(raw_bounds, str)
                or len(raw_bounds) != 4):
            raise ValueError(f"bounds must be a 4-tuple for {site_id!r}")
        values = [float(v) for v in raw_bounds]
        bounds: Bounds = (values[0], values[1], values[2], values[3])
        return cls(site_id=site_id, bounds=bounds, crs_epsg=crs)


@dataclass(frozen=True)
class Overlap:
    """One forbidden proximity event between a Gold site and a unit."""

    gold_site_id: str
    blocked_unit_id: str
    crs_epsg: int
    buffer_m: float
    overlap_west_east: bool
    overlap_south_north: bool


class GoldsetIsolationError(ValueError):
    """Raised when a Gold envelope intersects a blocked spatial unit."""


def _intervals_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 <= b1 and b0 <= a1


def _buffered(bounds: Bounds, buffer_m: float) -> Bounds:
    west, south, east, north = bounds
    return (west - buffer_m, south - buffer_m,
            east + buffer_m, north + buffer_m)


def overlaps_for_site(
    gold: Envelope, blocked_units: Sequence[Envelope], buffer_m: float,
) -> list[Overlap]:
    """Return every blocked unit touching ``gold`` within ``buffer_m``."""
    if buffer_m < 0:
        raise ValueError("buffer_m must be non-negative")
    found: list[Overlap] = []
    gw, gs, ge, gn = _buffered(gold.bounds, buffer_m)
    for unit in blocked_units:
        if unit.crs_epsg != gold.crs_epsg:
            raise GoldsetIsolationError(
                f"cannot check isolation across CRS: {gold.site_id!r} "
                f"EPSG:{gold.crs_epsg} vs {unit.site_id!r} "
                f"EPSG:{unit.crs_epsg}; reproject first")
        uw, us, ue, un = unit.bounds
        x_overlap = _intervals_overlap(gw, ge, uw, ue)
        y_overlap = _intervals_overlap(gs, gn, us, un)
        if x_overlap and y_overlap:
            found.append(Overlap(
                gold_site_id=gold.site_id,
                blocked_unit_id=unit.site_id,
                crs_epsg=gold.crs_epsg,
                buffer_m=float(buffer_m),
                overlap_west_east=x_overlap,
                overlap_south_north=y_overlap))
    return found


def find_gold_overlaps(
    gold_sites: Sequence[Envelope],
    blocked_units: Sequence[Envelope],
    *,
    buffer_m: float = 0.0,
) -> list[Overlap]:
    """All Gold/blocked proximity events across every Gold site."""
    events: list[Overlap] = []
    for gold in gold_sites:
        events.extend(overlaps_for_site(gold, blocked_units, buffer_m))
    return events


def assert_gold_isolated(
    gold_sites: Sequence[Envelope],
    blocked_units: Sequence[Envelope],
    *,
    buffer_m: float = 0.0,
) -> None:
    """Freeze gate: raise on any Gold/blocked overlap, otherwise return."""
    events = find_gold_overlaps(
        gold_sites, blocked_units, buffer_m=buffer_m)
    if events:
        lines = [
            f"  {e.gold_site_id} <-> {e.blocked_unit_id} "
            f"(EPSG:{e.crs_epsg}, buffer={e.buffer_m:g} m)"
            for e in events]
        raise GoldsetIsolationError(
            "GoldSet isolation violated; GOLD sites touch blocked "
            "(train/val/threshold/weak-tuning/hp-search) units:\n"
            + "\n".join(lines))


def envelopes_from_records(
    records: Sequence[Mapping[str, object]],
) -> list[Envelope]:
    """Parse a manifest sequence into envelopes."""
    return [Envelope.from_record(row) for row in records]


__all__ = [
    "Bounds",
    "Envelope",
    "GoldsetIsolationError",
    "Overlap",
    "assert_gold_isolated",
    "envelopes_from_records",
    "find_gold_overlaps",
    "overlaps_for_site",
]
