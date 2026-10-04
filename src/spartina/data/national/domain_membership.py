"""Deterministic, target-independent mainland coastal-domain membership.

Issue #17 separates two concepts that v0 conflated:

* **grid cell geometry** -- the immutable W5/W10/W20 China-Albers lattice
  and its cell IDs (see :mod:`spartina.data.national.grid`); geometry and
  IDs never change after a revision;
* **domain membership** -- the versioned decision of whether a cell is in
  the *mainland China coastal domain*.  v0 included every cell that
  overlapped the corridor geometry; v1 additionally tests coastal
  ownership so that the corridor's border-proximity slivers cannot admit
  foreign land (North Korea / Russia / Vietnam) or open-sea edge cells.

Membership evidence is strictly target-independent:

* admin ownership comes from Natural Earth admin-0 polygons;
* land / coastline geometry comes from GSHHS L1;
* nearshore islands follow the fixed a-priori rule
  (area <= 100 km^2, representative point within 25 km of the China
  mainland, representative point in no foreign admin polygon);
* seaward water cells are admitted only when Chinese land is their
  nearest landfall within the corridor half-width.

Murray intertidal and JRC surface-water summaries are *context only*.
They are deliberately absent from :func:`decide_membership`, so they can
never label Spartina, never anchor a foreign intertidal flat into the
domain, and never silently resolve an ambiguous border cell -- those stay
``PROVISIONAL_UNRESOLVED`` for human review.

No observation counts, image availability, Spartina labels or model
outputs are inputs to the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

# --- membership versions -------------------------------------------------

V0_MEMBERSHIP: Final[str] = "INCLUDED"
"""Every v0 registry cell was admitted solely by corridor overlap."""

# --- decision tokens (mandate: closed vocabulary) ------------------------

KEEP_MAINLAND_COASTAL: Final[str] = "KEEP_MAINLAND_COASTAL"
"""Cell intersects China-administered mainland, or is open water whose
nearest landfall is the China mainland coast within the corridor."""

KEEP_ISLAND_COASTAL: Final[str] = "KEEP_ISLAND_COASTAL"
"""Cell is anchored by a qualifying Chinese nearshore island."""

EXCLUDE_DOMAIN_ARTIFACT: Final[str] = "EXCLUDE_DOMAIN_ARTIFACT"
"""Cell contains no Chinese land and its nearest landfall is foreign or
outside corridor reach -- a corridor-geometry sliver, not China coast."""

PROVISIONAL_UNRESOLVED: Final[str] = "PROVISIONAL_UNRESOLVED"
"""Deterministic evidence conflicts (border tie, unadministered land);
human review required.  Context layers must not auto-resolve these."""

DECISION_TOKENS: Final[tuple[str, ...]] = (
    KEEP_MAINLAND_COASTAL,
    KEEP_ISLAND_COASTAL,
    EXCLUDE_DOMAIN_ARTIFACT,
    PROVISIONAL_UNRESOLVED,
)

# --- reason codes ---------------------------------------------------------

REASON_CHINA_MAINLAND_LAND: Final[str] = "CHINA_MAINLAND_LAND"
REASON_CHINA_SEAWARD_WATER: Final[str] = "CHINA_SEAWARD_WATER"
REASON_CHINA_NEARSHORE_ISLAND: Final[str] = "CHINA_NEARSHORE_ISLAND"
REASON_FOREIGN_LAND_ONLY: Final[str] = "FOREIGN_LAND_ONLY"
REASON_OPEN_WATER_OUTSIDE_REACH: Final[str] = "OPEN_WATER_OUTSIDE_REACH"
REASON_FOREIGN_NEARER_LANDFALL: Final[str] = "FOREIGN_NEARER_LANDFALL"
REASON_BORDER_LANDFALL_TIE: Final[str] = "BORDER_LANDFALL_TIE"
REASON_UNADMINISTERED_LAND: Final[str] = "UNADMINISTERED_LAND"
REASON_CONTESTED_ADMIN_NEARSHORE: Final[str] = "CONTESTED_ADMIN_NEARSHORE"
REASON_CONTESTED_OUTSIDE_REACH: Final[str] = "CONTESTED_OUTSIDE_REACH"
REASON_MISSING_EVIDENCE: Final[str] = "MISSING_EVIDENCE"

# Natural Earth admin-0 map units normalised to PRC ownership: Hong Kong
# and Macao are Chinese Special Administrative Regions, never "foreign".
CHINA_ADMIN_UNITS: Final[frozenset[str]] = frozenset(
    {"China", "Hong Kong S.A.R.", "Macao S.A.R"}
)
# Map units with contested administration.  Taiwan-administered land
# inside the mainland corridor is the Kinmen/Matsu archipelago (a few km
# off Fujian); it is retained as PROVISIONAL, never silently excluded or
# claimed.  Taiwan island itself lies outside corridor reach.
CONTESTED_ADMIN_UNITS: Final[frozenset[str]] = frozenset(
    {"Taiwan", "Scarborough Reef"}
)

# --- admin / island classes ----------------------------------------------

ADMIN_MAINLAND_CHINA: Final[str] = "MAINLAND_CHINA"
ADMIN_MIXED_CHINA_FOREIGN: Final[str] = "MIXED_CHINA_FOREIGN"
ADMIN_ISLAND_CHINA: Final[str] = "NEARSHORE_ISLAND_CHINA"
ADMIN_WATER_NEAR_CHINA: Final[str] = "WATER_NEAR_CHINA"
ADMIN_FOREIGN_ONLY: Final[str] = "FOREIGN_ONLY"
ADMIN_CONTESTED: Final[str] = "CONTESTED_ADMIN"
ADMIN_WATER_FOREIGN_NEAR: Final[str] = "WATER_FOREIGN_NEAR"
ADMIN_WATER_OPEN: Final[str] = "WATER_OPEN"
ADMIN_UNRESOLVED: Final[str] = "UNRESOLVED"

ISLAND_MAINLAND: Final[str] = "MAINLAND"
ISLAND_MAINLAND_PLUS: Final[str] = "MAINLAND_PLUS_NEARSHORE_ISLAND"
ISLAND_NEARSHORE: Final[str] = "NEARSHORE_ISLAND"
ISLAND_NONE: Final[str] = "NONE"

# --- fixed a-priori rule parameters --------------------------------------

ISLAND_MAX_AREA_M2: Final[int] = 100_000_000
"""Qualifying nearshore islands are at most 100 km^2 (v0 rule)."""

ISLAND_NEAR_M: Final[int] = 25_000
"""Representative point must be within 25 km of the China mainland."""

MIN_LAND_TOUCH_M2: Final[float] = 100.0
"""Ignore sub-100 m^2 hairline polygon touches (projection slivers)."""

BORDER_TIE_M: Final[float] = 500.0
"""Landfall distance difference under which a seaward cell is an
unresolved border-estuary tie rather than assigned to either state."""


class MembershipVersion(str, Enum):
    """Membership registry versions."""

    V0 = "v0"
    V1_CANDIDATE = "v1_candidate"


@dataclass(frozen=True)
class CellMembershipEvidence:
    """Target-independent geometric evidence for one lattice cell.

    All areas are m^2 in the equal-area China Albers CRS; distances are
    minimum planar distances (m) between the cell polygon and the
    respective land union.  ``None`` distance means evidence could not be
    computed and the decision must be PROVISIONAL rather than guessed.
    """

    cell_id: str
    cell_area_m2: float
    corridor_half_width_m: float
    china_mainland_area_m2: float
    china_island_area_m2: float
    foreign_land_area_m2: float
    unadministered_land_area_m2: float
    dist_to_china_mainland_m: float | None
    dist_to_foreign_land_m: float | None
    contested_admin_area_m2: float = 0.0
    """Land under contested admin units (Kinmen/Matsu etc.)."""
    foreign_landfall_area_m2: float = 0.0
    """GSHHS land inside no admin polygon whose nearest administered
    landfall is foreign (coast-generalization gaps / v0 island-rule false
    positives at land borders)."""
    island_max_area_m2: int = ISLAND_MAX_AREA_M2
    island_near_m: int = ISLAND_NEAR_M
    border_tie_m: float = BORDER_TIE_M
    min_land_touch_m2: float = MIN_LAND_TOUCH_M2

    @property
    def china_land_area_m2(self) -> float:
        return self.china_mainland_area_m2 + self.china_island_area_m2

    @property
    def foreign_evidence_area_m2(self) -> float:
        return self.foreign_land_area_m2 + self.foreign_landfall_area_m2

    @property
    def total_land_area_m2(self) -> float:
        return (
            self.china_mainland_area_m2
            + self.china_island_area_m2
            + self.foreign_land_area_m2
            + self.foreign_landfall_area_m2
            + self.unadministered_land_area_m2
        )


@dataclass(frozen=True)
class MembershipDecision:
    """Membership decision with a single deterministic reason code."""

    decision: str
    reason: str
    admin_class: str
    island_class: str

    @property
    def is_kept(self) -> bool:
        return self.decision in (KEEP_MAINLAND_COASTAL, KEEP_ISLAND_COASTAL)


def island_classification(ev: CellMembershipEvidence) -> str:
    """Deterministic island class from area evidence."""
    mainland = ev.china_mainland_area_m2 >= ev.min_land_touch_m2
    island = ev.china_island_area_m2 >= ev.min_land_touch_m2
    if mainland and island:
        return ISLAND_MAINLAND_PLUS
    if mainland:
        return ISLAND_MAINLAND
    if island:
        return ISLAND_NEARSHORE
    return ISLAND_NONE


def _missing(ev: CellMembershipEvidence) -> bool:
    """Landfall distances are required for cells without Chinese land."""
    return ev.dist_to_china_mainland_m is None or ev.dist_to_foreign_land_m is None


def decide_membership(ev: CellMembershipEvidence) -> MembershipDecision:
    """Apply the deterministic v1 mainland coastal-domain rule.

    Ordering is fixed and each branch is target-independent:

    1. Any non-sliver China-mainland land in the cell -> keep as mainland
       coastal (transboundary cells with real Chinese land are kept, and
       the foreign share stays recorded as evidence).
    2. Contested-admin land present (Kinmen/Matsu): nearshore within
       corridor reach -> provisional for human review; beyond reach
       (Taiwan island) -> exclude.  A Chinese nearshore-islet sliver does
       not override a contested-dominated cell.
    3. Otherwise a qualifying nearshore island -> keep as island coastal.
    4. Otherwise evidence must be complete; missing landfall distances
       -> provisional (never guess).
    5. Unadministered GSHHS land >= 1 % of the cell -> provisional
       (sovereignty ambiguous).
    6. Foreign land / foreign-nearer / out-of-reach water -> exclude as a
       corridor-geometry artifact.
    7. Remaining open-water cells are kept only when Chinese land is the
       nearest landfall within corridor reach and it is not a border tie.
    """
    island_cls = island_classification(ev)

    # 1. China-administered mainland land present (includes Chinese SARs;
    #    a contested sliver alongside real Chinese mainland stays kept).
    if ev.china_mainland_area_m2 >= ev.min_land_touch_m2:
        admin = (
            ADMIN_MIXED_CHINA_FOREIGN
            if ev.foreign_evidence_area_m2 >= ev.min_land_touch_m2
            else ADMIN_MAINLAND_CHINA
        )
        return MembershipDecision(
            KEEP_MAINLAND_COASTAL, REASON_CHINA_MAINLAND_LAND, admin, island_cls
        )

    # 2. Contested administration is never silently claimed or deleted.
    #    Distance completeness is enforced first (never guess).
    if ev.contested_admin_area_m2 >= ev.min_land_touch_m2:
        if _missing(ev):
            return MembershipDecision(
                PROVISIONAL_UNRESOLVED,
                REASON_MISSING_EVIDENCE,
                ADMIN_UNRESOLVED,
                island_cls,
            )
        d_china_c = ev.dist_to_china_mainland_m
        assert d_china_c is not None  # _missing() returned False above
        if d_china_c <= ev.corridor_half_width_m:
            return MembershipDecision(
                PROVISIONAL_UNRESOLVED,
                REASON_CONTESTED_ADMIN_NEARSHORE,
                ADMIN_CONTESTED,
                island_cls,
            )
        return MembershipDecision(
            EXCLUDE_DOMAIN_ARTIFACT,
            REASON_CONTESTED_OUTSIDE_REACH,
            ADMIN_CONTESTED,
            island_cls,
        )

    # 3. Qualifying Chinese nearshore island anchors the cell.
    if ev.china_island_area_m2 >= ev.min_land_touch_m2:
        return MembershipDecision(
            KEEP_ISLAND_COASTAL,
            REASON_CHINA_NEARSHORE_ISLAND,
            ADMIN_ISLAND_CHINA,
            island_cls,
        )

    # 4. From here the cell has no Chinese land: landfall distances decide.
    if _missing(ev):
        return MembershipDecision(
            PROVISIONAL_UNRESOLVED,
            REASON_MISSING_EVIDENCE,
            ADMIN_UNRESOLVED,
            island_cls,
        )

    d_china = ev.dist_to_china_mainland_m
    d_foreign = ev.dist_to_foreign_land_m
    assert d_china is not None and d_foreign is not None  # _missing False above

    # 5. Material land attributed to no admin-0 polygon is unresolved.
    if ev.unadministered_land_area_m2 >= 0.01 * ev.cell_area_m2:
        return MembershipDecision(
            PROVISIONAL_UNRESOLVED,
            REASON_UNADMINISTERED_LAND,
            ADMIN_UNRESOLVED,
            island_cls,
        )

    # 6. Foreign land inside the cell (admin polygon or foreign-landfall
    # islands): a corridor sliver over a neighbour.
    if ev.foreign_evidence_area_m2 >= ev.min_land_touch_m2:
        return MembershipDecision(
            EXCLUDE_DOMAIN_ARTIFACT,
            REASON_FOREIGN_LAND_ONLY,
            ADMIN_FOREIGN_ONLY,
            island_cls,
        )

    # 7. Pure water cell: nearest-landfall principle within corridor reach.
    if d_china > ev.corridor_half_width_m:
        return MembershipDecision(
            EXCLUDE_DOMAIN_ARTIFACT,
            REASON_OPEN_WATER_OUTSIDE_REACH,
            ADMIN_WATER_OPEN,
            island_cls,
        )

    if abs(d_china - d_foreign) <= ev.border_tie_m:
        return MembershipDecision(
            PROVISIONAL_UNRESOLVED,
            REASON_BORDER_LANDFALL_TIE,
            ADMIN_UNRESOLVED,
            island_cls,
        )

    if d_china < d_foreign:
        return MembershipDecision(
            KEEP_MAINLAND_COASTAL,
            REASON_CHINA_SEAWARD_WATER,
            ADMIN_WATER_NEAR_CHINA,
            island_cls,
        )

    return MembershipDecision(
        EXCLUDE_DOMAIN_ARTIFACT,
        REASON_FOREIGN_NEARER_LANDFALL,
        ADMIN_WATER_FOREIGN_NEAR,
        island_cls,
    )
