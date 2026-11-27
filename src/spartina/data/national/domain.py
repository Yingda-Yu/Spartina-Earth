"""Target-independent national coastal domain definitions (Issue #14).

The corridor must NOT be defined by buffering a Spartina product
(instruction sections 19, 27): candidate widths are chosen on coastal
geomorphology, intertidal / tidal-wetland distribution, shoreline
uncertainty, management zones and cost.  Positive-label coverage of
any product is a diagnostic only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from .grid import CELL_SIZE_M


class CorridorWidth(int, Enum):
    """Candidate symmetric coastal corridor half-widths (metres)."""

    W_5KM = 5_000
    W_10KM = 10_000
    W_20KM = 20_000


# Positive coverage is reported at every candidate width so the choice
# can never become "the width that just covers the positives".
ALL_CORRIDOR_WIDTHS: Final[tuple[CorridorWidth, ...]] = (
    CorridorWidth.W_5KM,
    CorridorWidth.W_10KM,
    CorridorWidth.W_20KM,
)


class Stratum(str, Enum):
    """National cell strata (instruction section 28).

    A cell can carry several flags at once; a cell's status is the set
    of strata it belongs to.  ``UNLABELED_COASTAL`` is an
    absence-of-evidence state, never an ecological negative
    (instruction section 29).
    """

    COASTAL_RELEVANT = "COASTAL_RELEVANT"
    SILVER_2015_POSITIVE = "SILVER_2015_POSITIVE"
    SILVER_2015_NEARBY = "SILVER_2015_NEARBY"
    CMSA_POSITIVE_HISTORY = "CMSA_POSITIVE_HISTORY"
    CMSSM_2020_POSITIVE = "CMSSM_2020_POSITIVE"
    UNLABELED_COASTAL = "UNLABELED_COASTAL"
    MANAGEMENT_EVIDENCE_AVAILABLE = "MANAGEMENT_EVIDENCE_AVAILABLE"
    GOLD_EVIDENCE_TARGET = "GOLD_EVIDENCE_TARGET"


# Cells with no positive evidence inside NEARBY_RADIUS_M while still
# intersecting the corridor are SILVER_2015_NEARBY.  The radius is a
# fixed design parameter (one standard 10 km cell ring), never fitted
# to labels.
NEARBY_RADIUS_M: Final[int] = CELL_SIZE_M


@dataclass(frozen=True)
class DomainDecisionInputs:
    """Geomorphology-driven width-selection inputs (evidence, not labels).

    Field values summarise target-independent layers; positive-product
    coverage is supplied separately and never enters the decision.
    """

    intertidal_onshore_extent_m_p90: float | None = None
    tidal_wetland_onshore_extent_m_p90: float | None = None
    shoreline_position_uncertainty_m: float | None = None
    management_zone_halfwidth_m: float | None = None
    cell_size_m: int = CELL_SIZE_M

    def recommended_width(self) -> CorridorWidth:
        """Pick the narrowest candidate covering the geomorphic envelope.

        Rule: max of the independent physical envelopes, rounded up to
        the next candidate width; 20 km is the fallback only while
        envelopes are unmeasured.  Positive-label coverage is ignored.
        """
        envelopes = [
            v
            for v in (
                self.intertidal_onshore_extent_m_p90,
                self.tidal_wetland_onshore_extent_m_p90,
                self.shoreline_position_uncertainty_m,
                self.management_zone_halfwidth_m,
            )
            if v is not None
        ]
        needed = max(envelopes, default=float(CorridorWidth.W_20KM))
        for width in ALL_CORRIDOR_WIDTHS:
            if needed <= float(width):
                return width
        return CorridorWidth.W_20KM
