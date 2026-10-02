"""Dynamic coastal-state metadata schema (M2.1a2, Issue #12, section 9).

The fixed AnalysisCell is time-stable; the actual land/water/intertidal
context at a given time is a separate, date-keyed record. This module
only defines the schema and produces a handful of clearly-labelled
SIMULATED example rows. No multi-decade shoreline products are generated
at this stage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spartina.data.gee.selection import canonical_fingerprint

STATUS_OBSERVED: str = "OBSERVED"
STATUS_MODELED: str = "MODELED"
STATUS_PROXY: str = "PROXY"
STATUS_MISSING: str = "MISSING"
STATUS_SIMULATED_EXAMPLE: str = "SIMULATED_NOT_DERIVED"

COASTAL_STATE_STATUSES: tuple[str, ...] = (
    STATUS_OBSERVED,
    STATUS_MODELED,
    STATUS_PROXY,
    STATUS_MISSING,
    STATUS_SIMULATED_EXAMPLE,
)

SHORELINE_SOURCE_NONE: str = "NONE_DATE_SPECIFIC_SHORELINE_NOT_DERIVED"


@dataclass(frozen=True)
class CoastalStateRecord:
    cell_id: str
    record_date: str  # UTC ISO date; the dynamic record is never year-only
    land_fraction: float | None
    water_fraction: float | None
    intertidal_proxy: float | None
    inundation_proxy: float | None
    shoreline_source: str
    shoreline_version: str
    status: str
    notes: str

    def as_row(self) -> dict[str, Any]:
        row = {
            "cell_id": self.cell_id,
            "record_date": self.record_date,
            "land_fraction": self.land_fraction,
            "water_fraction": self.water_fraction,
            "intertidal_proxy": self.intertidal_proxy,
            "inundation_proxy": self.inundation_proxy,
            "shoreline_source": self.shoreline_source,
            "shoreline_version": self.shoreline_version,
            "status": self.status,
            "notes": self.notes,
        }
        row["row_fingerprint"] = canonical_fingerprint(row)
        return row


COASTAL_STATE_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "record_date",
    "land_fraction",
    "water_fraction",
    "intertidal_proxy",
    "inundation_proxy",
    "shoreline_source",
    "shoreline_version",
    "status",
    "notes",
    "row_fingerprint",
)

# Tide context fields are declared here so ObservationEvent tables have a
# stable contract before any tide bytes exist (Issue #12 section 35).
TIDE_CONTEXT_FIELDS: tuple[str, ...] = (
    "observed_tide_value_m",
    "observed_tide_source",
    "observed_tide_utc",
    "observed_tide_uncertainty_m",
    "observed_tide_status",
    "modeled_tide_value_m",
    "modeled_tide_source",
    "modeled_tide_utc",
    "modeled_tide_uncertainty_m",
    "modeled_tide_status",
    "inundation_proxy_value",
    "inundation_proxy_source",
    "inundation_proxy_status",
    "water_fraction_proxy_value",
    "water_fraction_proxy_source",
    "water_fraction_proxy_status",
    "tide_context_status",
)
