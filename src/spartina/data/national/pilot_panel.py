"""First national real-pixel pilot panel logic (Issue #19, M2.5).

Pure helpers for verifying the preselected 20-cell panel against the
frozen W10 v1.1 core registry and for labelling panel context. All I/O
lives in the freeze script; nothing here touches Earth Engine.

The panel itself was selected *before* any pixel evidence existed
(``docs/data/national/FIRST_PIXEL_PILOT_DESIGN_v0.json``). Issue #19
freezes that same panel against ``W10_DOMAIN_V1_CORE_FROZEN``; cells are
never substituted because of imagery quality or label appearance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

#: Domain version against which the pilot panel is production-eligible.
PANEL_DOMAIN_VERSION: Final[str] = "W10_DOMAIN_V1_CORE_FROZEN"
PANEL_REGISTRY_NAME: Final[str] = "china_coastal_cells_v1_1_core_frozen.csv"
PANEL_ID_SPACE_PREFIX: Final[str] = "CNA10K-"


class PanelError(ValueError):
    """A pilot panel preflight check failed hard (no silent substitution)."""


# ---------------------------------------------------------------------------
# Anchor-year / sensor plan (Phase B; minimal anchor design, no annual stack)
# ---------------------------------------------------------------------------

class SensorYearStatus(Enum):
    """Honest absence/presence states for cell x sensor x year.

    Plain ``Enum`` (not ``str, Enum``) to stay valid on Python 3.10 under
    the pyupgrade rules; compare against members and read ``.value`` for
    the serialized token.
    """

    SENSOR_NOT_OPERATIONAL = "SENSOR_NOT_OPERATIONAL"
    NO_SCENE = "NO_SCENE"
    NO_ELIGIBLE_EVENT = "NO_ELIGIBLE_EVENT"
    SELECTED = "SELECTED"
    EXPORTED = "EXPORTED"
    EXPORT_FAILED = "EXPORT_FAILED"


@dataclass(frozen=True)
class AnchorSlot:
    """One predeclared sensor x anchor-year slot of the pilot design."""

    sensor: str
    year: int
    priority: str  # PRIMARY | SECONDARY
    note: str
    fallback_sensors: tuple[str, ...] = ()
    #: S1 exports one product per orbit pass; optical/S2 one per slot.
    per_pass: bool = False


#: Order is the planned attempt order per year. The 2000 optical anchor
#: prefers L5 and accepts L7 only when L5 has no eligible event (both are
#: pre-SLC-off in 2000); the event plan records which platform supplied
#: the event. 2020 is the highest-priority multimodal anchor. The 2021
#: S1/S2 anchor aligns to CMSA 2021.
ANCHOR_SLOTS: Final[tuple[AnchorSlot, ...]] = (
    AnchorSlot("landsat5", 1990, "PRIMARY",
               "Landsat 5 TM Collection 2 L2 where real eligible scenes exist"),
    AnchorSlot("landsat5", 2000, "PRIMARY",
               "Landsat 5 TM preferred; Landsat 7 ETM+ is the only fallback "
               "when L5 has no eligible event (2000 is SLC-on for both)",
               fallback_sensors=("landsat7",)),
    AnchorSlot("landsat8", 2015, "PRIMARY",
               "Landsat 8 OLI aligned with GEODATA 2015"),
    AnchorSlot("sentinel1", 2015, "SECONDARY",
               "S1 IW GRD VV/VH; one product per orbit pass; exact "
               "acquisition/event semantics required (operations began 2015)",
               per_pass=True),
    AnchorSlot("sentinel2", 2015, "SECONDARY",
               "S2A only after 2015-06-23; absent scenes are honest "
               "NO_SCENE, never fabricated"),
    AnchorSlot("landsat8", 2020, "PRIMARY",
               "Landsat 8 OLI aligned with the three-product 2020 audit"),
    AnchorSlot("sentinel1", 2020, "PRIMARY",
               "S1 IW GRD VV/VH; ASC and DESC kept separate, never fused",
               per_pass=True),
    AnchorSlot("sentinel2", 2020, "PRIMARY",
               "S2 SR native 10 m; same-datatake tiles only, s2_scl_qa_v1_1"),
    AnchorSlot("sentinel1", 2021, "PRIMARY",
               "S1 anchor aligned with CMSA 2021 reference availability",
               per_pass=True),
    AnchorSlot("sentinel2", 2021, "PRIMARY",
               "S2 anchor aligned with CMSA 2021 reference availability"),
    AnchorSlot("landsat8", 2021, "SECONDARY",
               "L8 2021 only where it adds a valid cloud-free observation"),
)

ANCHOR_YEARS: Final[tuple[int, ...]] = (1990, 2000, 2015, 2020, 2021)

#: First year of valid observations per sensor (GEE collection reality).
SENSOR_FIRST_YEAR: Final[dict[str, int]] = {
    "landsat5": 1984,
    "landsat7": 1999,
    "landsat8": 2013,
    "landsat9": 2022,
    "sentinel1": 2015,
    "sentinel2": 2015,
}


# ---------------------------------------------------------------------------
# Panel verification
# ---------------------------------------------------------------------------

def verify_panel(
    panel_cell_ids: list[str],
    registry_cell_ids: set[str],
    membership: dict[str, str],
    production_eligible: dict[str, bool],
) -> dict[str, list[str]]:
    """Verify every panel cell exists, is KEEP, and is production eligible.

    Returns ``{"ok": [...], "rejected": [...]}``; raises
    :class:`PanelError` on any hard eligibility failure because replacing a
    panel cell requires an owner-visible STOP, never a silent swap.
    """
    if len(panel_cell_ids) != len(set(panel_cell_ids)):
        raise PanelError("pilot panel contains duplicate cell ids")
    rejected: list[str] = []
    ok: list[str] = []
    for cell_id in panel_cell_ids:
        if not cell_id.startswith(PANEL_ID_SPACE_PREFIX):
            raise PanelError(f"panel cell id outside CNA10K id space: {cell_id}")
        if cell_id not in registry_cell_ids:
            rejected.append(cell_id)
            continue
        status = membership.get(cell_id, "")
        if not status.startswith("KEEP_"):
            rejected.append(cell_id)
            continue
        if not production_eligible.get(cell_id, False):
            rejected.append(cell_id)
            continue
        ok.append(cell_id)
    if rejected:
        raise PanelError(
            "pilot cells fail the W10 v1.1 KEEP/production preflight "
            "(owner STOP required before any substitution): "
            + ", ".join(rejected))
    return {"ok": ok, "rejected": rejected}


# ---------------------------------------------------------------------------
# Context labelling (pure)
# ---------------------------------------------------------------------------

#: Province (Natural Earth name_en) -> deterministic coastal segment. The
#: mapping is fixed before event selection and documented in the manifest;
#: it groups coastal provinces by the adjacent China marginal sea.
PROVINCE_SEGMENT: Final[dict[str, str]] = {
    "Liaoning": "BOHAI_YELLOW_SEA",
    "Hebei": "BOHAI_SEA",
    "Tianjin": "BOHAI_SEA",
    "Shandong": "BOHAI_YELLOW_SEA",
    "Jiangsu": "YELLOW_SEA",
    "Shanghai": "EAST_CHINA_SEA",
    "Zhejiang": "EAST_CHINA_SEA",
    "Fujian": "TAIWAN_STRAIT",
    "Guangdong": "SOUTH_CHINA_SEA",
    "Guangxi": "BEIBU_GULF",
    "Hainan": "SOUTH_CHINA_SEA",
    "Taiwan": "TAIWAN_STRAIT",
}

UNKNOWN_SEGMENT: Final[str] = "UNKNOWN"


def coastal_segment(province_name: str | None) -> str:
    """Map an attributed province name to the fixed coastal-segment token."""
    if not province_name:
        return UNKNOWN_SEGMENT
    return PROVINCE_SEGMENT.get(province_name, UNKNOWN_SEGMENT)


def label_agreement_category_2020(
    geodata_pos: bool, cmsa_pos: bool, cmssm_pos: bool
) -> str:
    """Deterministic 2020 three-product presence category for one cell.

    Categories describe *presence agreement*, never accuracy:
      ALL_THREE_PRESENT / GEODATA_ONLY / CMSA_CMSSM_PRESENT /
      GEODATA_CMSA_ONLY / GEODATA_CMSSM_ONLY / CMSA_ONLY / CMSSM_ONLY /
      NONE_PRESENT.
    """
    g, c, m = bool(geodata_pos), bool(cmsa_pos), bool(cmssm_pos)
    if g and c and m:
        return "ALL_THREE_PRESENT"
    if g and not c and not m:
        return "GEODATA_ONLY"
    if not g and c and m:
        return "CMSA_CMSSM_PRESENT"
    if g and c and not m:
        return "GEODATA_CMSA_ONLY"
    if g and not c and m:
        return "GEODATA_CMSSM_ONLY"
    if not g and c and not m:
        return "CMSA_ONLY"
    if not g and not c and m:
        return "CMSSM_ONLY"
    return "NONE_PRESENT"


__all__ = [
    "ANCHOR_SLOTS",
    "ANCHOR_YEARS",
    "PANEL_DOMAIN_VERSION",
    "PANEL_REGISTRY_NAME",
    "AnchorSlot",
    "PanelError",
    "PROVINCE_SEGMENT",
    "SENSOR_FIRST_YEAR",
    "SensorYearStatus",
    "coastal_segment",
    "label_agreement_category_2020",
    "verify_panel",
]
