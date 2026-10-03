"""Tier 0-3 national scale / storage / cost model (section 42).

Every number this model emits is a **model estimate**, not an
executed result: input counts must come from measured artifacts
(domain cell counts, the M2.1b (#13) real-product byte audit) and all
assumptions are explicit fields of :class:`CostAssumptions` with
provenance strings.  No fabricated observation counts or volumes ever
appear as measured data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

# Byte basis: measured means from the executed M2.1b pilot (#13),
# 13 products / 8 HZB cells (aggregate manifest
# datasets/manifests/zhejiang_m21b_pilot_v0.json; 127,253,613 B total).
# Per-modality figures are pinned by the cost script reading that
# manifest; the defaults below are conservative documented priors.
DEFAULT_OPTICAL_S2_BYTES_PER_PRODUCT = 9_000_000
DEFAULT_OPTICAL_L_BYTES_PER_PRODUCT = 2_700_000
DEFAULT_SAR_S1_BYTES_PER_PRODUCT = 25_000_000


class Tier(str, Enum):
    TIER0 = "TIER0_METADATA_ONLY"
    TIER1 = "TIER1_POSITIVE_HISTORY_NEARBY"
    TIER2 = "TIER2_STANDARD_NATIONAL_MONITORING"
    TIER3 = "TIER3_FULL_COASTAL_ARCHIVE"


@dataclass(frozen=True)
class MonitoringPolicy:
    """Annual archive policy assumed for standard monitoring tiers."""

    s2_products_per_cell_year: int = 3
    landsat_products_per_cell_year: int = 3
    s1_products_per_cell_year: int = 6
    # Full archive: every eligible event passing the production QA gate.
    s2_eligible_events_per_cell_year: int = 12
    landsat_eligible_events_per_cell_year: int = 18
    s1_eligible_events_per_cell_year: int = 36


@dataclass(frozen=True)
class CostAssumptions:
    """Explicit model inputs (never silently hard-coded downstream)."""

    s2_bytes_per_product: int = DEFAULT_OPTICAL_S2_BYTES_PER_PRODUCT
    landsat_bytes_per_product: int = DEFAULT_OPTICAL_L_BYTES_PER_PRODUCT
    s1_bytes_per_product: int = DEFAULT_SAR_S1_BYTES_PER_PRODUCT
    products_per_gee_task: int = 1
    gee_task_seconds_per_product: float = 180.0
    census_bytes_per_cell_year: int = 4_096
    tier1_cell_fraction: float = 0.15
    tier2_cell_fraction: float = 1.0
    tier3_cell_fraction: float = 1.0
    years_archive: int = 42
    years_monitoring: int = 1
    positive_history_cells: int = 0
    policy: MonitoringPolicy = field(default_factory=MonitoringPolicy)
    provenance: tuple[str, ...] = (
        "M2.1b (#13) real byte audit, 8 HZB cells, 13 products, 121.4 MiB",
        "tier1_cell_fraction is a planning prior to be replaced by measured strata counts",
    )

    def validate(self) -> None:
        if not 0 < self.tier1_cell_fraction <= 1:
            raise ValueError("tier1_cell_fraction must be in (0,1]")
        for name, value in (
            ("s2_bytes_per_product", self.s2_bytes_per_product),
            ("landsat_bytes_per_product", self.landsat_bytes_per_product),
            ("s1_bytes_per_product", self.s1_bytes_per_product),
            ("census_bytes_per_cell_year", self.census_bytes_per_cell_year),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.products_per_gee_task < 1:
            raise ValueError("products_per_gee_task >= 1")
        if self.years_archive < self.years_monitoring:
            raise ValueError("archive horizon shorter than monitoring horizon")


@dataclass(frozen=True)
class TierEstimate:
    tier: Tier
    cells: int
    cell_years: int
    events: int
    products: int
    bytes_total: int
    gee_tasks: int
    estimated_runtime_seconds: float

    def to_dict(self) -> dict[str, object]:
        out = asdict(self)
        out["tier"] = self.tier.value
        out["gibibytes"] = round(self.bytes_total / 2**30, 3)
        out["estimated_runtime_hours"] = round(
            self.estimated_runtime_seconds / 3600.0, 2
        )
        return out


class NationalScaleModel:
    """Apply the cost model at the four defined tiers."""

    def __init__(self, coastal_cells: int, assumptions: CostAssumptions) -> None:
        assumptions.validate()
        if coastal_cells <= 0:
            raise ValueError("coastal_cells must be positive")
        self.coastal_cells = coastal_cells
        self.a = assumptions

    # ---- tier cell bookkeeping ------------------------------------
    def _tier1_cells(self) -> int:
        measured = self.a.positive_history_cells
        if measured:
            return measured
        return int(round(self.coastal_cells * self.a.tier1_cell_fraction))

    # ---- per-cell-year byte basis ---------------------------------
    def _standard_products_per_cell_year(self) -> int:
        policy = self.a.policy
        return (
            policy.s2_products_per_cell_year
            + policy.landsat_products_per_cell_year
            + policy.s1_products_per_cell_year
        )

    def _standard_bytes_per_cell_year(self) -> int:
        policy = self.a.policy
        return (
            policy.s2_products_per_cell_year * self.a.s2_bytes_per_product
            + policy.landsat_products_per_cell_year
            * self.a.landsat_bytes_per_product
            + policy.s1_products_per_cell_year * self.a.s1_bytes_per_product
        )

    def _full_events_per_cell_year(self) -> int:
        policy = self.a.policy
        return (
            policy.s2_eligible_events_per_cell_year
            + policy.landsat_eligible_events_per_cell_year
            + policy.s1_eligible_events_per_cell_year
        )

    def _full_bytes_per_cell_year(self) -> int:
        policy = self.a.policy
        return (
            policy.s2_eligible_events_per_cell_year * self.a.s2_bytes_per_product
            + policy.landsat_eligible_events_per_cell_year
            * self.a.landsat_bytes_per_product
            + policy.s1_eligible_events_per_cell_year * self.a.s1_bytes_per_product
        )

    # ---- tiers ------------------------------------------------------
    def tier0(self, census_years: int) -> TierEstimate:
        cell_years = self.coastal_cells * census_years
        bytes_total = (
            cell_years * self.a.census_bytes_per_cell_year
        )
        return TierEstimate(
            tier=Tier.TIER0,
            cells=self.coastal_cells,
            cell_years=cell_years,
            events=0,
            products=0,
            bytes_total=bytes_total,
            gee_tasks=0,
            estimated_runtime_seconds=0.0,
        )

    def _product_estimate(
        self, tier: Tier, cells: int, years: int, full_archive: bool
    ) -> TierEstimate:
        cell_years = cells * years
        if full_archive:
            events = cell_years * self._full_events_per_cell_year()
            bytes_total = cell_years * self._full_bytes_per_cell_year()
        else:
            events = cell_years * self._standard_products_per_cell_year()
            bytes_total = cell_years * self._standard_bytes_per_cell_year()
        tasks = events // max(1, self.a.products_per_gee_task)
        runtime = tasks * self.a.gee_task_seconds_per_product / max(
            1, self.a.products_per_gee_task
        )
        return TierEstimate(
            tier=tier,
            cells=cells,
            cell_years=cell_years,
            events=events,
            products=events,
            bytes_total=bytes_total,
            gee_tasks=tasks,
            estimated_runtime_seconds=runtime,
        )

    def tier1(self) -> TierEstimate:
        return self._product_estimate(
            Tier.TIER1, self._tier1_cells(), self.a.years_monitoring, False
        )

    def tier2(self) -> TierEstimate:
        return self._product_estimate(
            Tier.TIER2,
            int(round(self.coastal_cells * self.a.tier2_cell_fraction)),
            self.a.years_monitoring,
            False,
        )

    def tier3(self) -> TierEstimate:
        return self._product_estimate(
            Tier.TIER3,
            int(round(self.coastal_cells * self.a.tier3_cell_fraction)),
            self.a.years_archive,
            True,
        )

    def all_tiers(self, census_years: int) -> dict[str, dict[str, object]]:
        estimates = (
            self.tier0(census_years),
            self.tier1(),
            self.tier2(),
            self.tier3(),
        )
        return {e.tier.value: e.to_dict() for e in estimates}

    def write_json(self, census_years: int, path: Path | str) -> None:
        payload = {
            "model": "national_tier_cost_model_v0",
            "coastal_cells": self.coastal_cells,
            "assumptions": asdict(self.a),
            "estimates": self.all_tiers(census_years),
        }
        Path(path).write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
