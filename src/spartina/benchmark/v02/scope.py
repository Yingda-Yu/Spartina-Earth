"""Issue #21 Phase H -- export scope accounting against frozen hard caps.

Pure arithmetic over the frozen acquisition plans and a landed-bytes
table measured from Issue #19 products. Nothing here trims scientific
support to fit a cap: an over-cap projection is a STOP verdict only.

GEE component tasks follow the Issue #19 V2 production contracts:
Sentinel-2 event -> (sr, valid) = 2 tasks; Sentinel-1 primary pair ->
(vvvh) = 1 task (the s1_dualpol_valid_v2 token is derived locally, not
a GEE task); each Landsat observation -> (sr, valid, qapixel) = 3.
"""

from __future__ import annotations

from typing import Any, Final

SCOPE_NAME: Final[str] = "V0_2_EXPORT_SCOPE_ESTIMATE"

#: Issue #21 hard owner-review stops.
MAX_NEW_CELLS: Final[int] = 96
MAX_LANDED_EO_BYTES: Final[int] = 40 * 1024**3
MAX_GEE_COMPONENT_TASKS: Final[int] = 10_000

#: GEE component tasks per eligible event (Issue #19 V2 contracts).
COMPONENT_TASKS: Final[dict[str, int]] = {
    "sentinel2": 2,   # sr, valid
    "sentinel1": 1,   # vvvh (valid_v2 derived locally)
    "landsat5": 3,    # sr, valid, qapixel
    "landsat7": 3,
    "landsat8": 3,
}

VERDICT_PROCEED: Final[str] = "WITHIN_CAP_PROCEED_PHASE_H_EXPORT"
VERDICT_STOP: Final[str] = "STOP_OWNER_REVIEW_CAP_EXCEEDED"


def estimate_scope(
    *, n_cells: int,
    s2_events: int,
    s1_pairs: int,
    landsat_observations: int,
    size_table: dict[str, int],
    byte_quantile: str,
) -> dict[str, Any]:
    """Project component-task counts and landed bytes.

    ``size_table`` maps product kind keys ("s2_event", "s1_pair",
    "landsat_observation") to a per-product landed-byte figure measured
    from Issue #19 pilot products (quantile named by
    ``byte_quantile``). Only GEE-exported components are counted; the
    locally derived S1 token bytes are recorded separately.
    """
    tasks = {
        "sentinel2": s2_events * COMPONENT_TASKS["sentinel2"],
        "sentinel1": s1_pairs * COMPONENT_TASKS["sentinel1"],
        "landsat": landsat_observations * COMPONENT_TASKS["landsat8"],
    }
    total_tasks = sum(tasks.values())
    projected_bytes = (
        s2_events * size_table["s2_event"]
        + s1_pairs * size_table["s1_pair"]
        + landsat_observations * size_table["landsat_observation"])
    caps = {
        "new_cells": MAX_NEW_CELLS,
        "landed_eo_bytes": MAX_LANDED_EO_BYTES,
        "gee_component_tasks": MAX_GEE_COMPONENT_TASKS,
    }
    measured = {"new_cells": n_cells,
                "landed_eo_bytes": projected_bytes,
                "gee_component_tasks": total_tasks}
    breaches = {
        key: {"cap": caps[key], "projected": measured[key]}
        for key in caps if measured[key] > caps[key]}
    return {
        "product": SCOPE_NAME,
        "issue": 21,
        "phase": "H",
        "counts": {
            "new_cells": n_cells,
            "s2_eligible_events": s2_events,
            "s1_primary_pairs_lte7d": s1_pairs,
            "landsat_eligible_observations": landsat_observations,
        },
        "component_task_contract": dict(COMPONENT_TASKS),
        "component_tasks_by_sensor": tasks,
        "projected_gee_component_tasks": total_tasks,
        "byte_table_quantile": byte_quantile,
        "size_table_bytes_per_product": dict(size_table),
        "projected_landed_eo_bytes": projected_bytes,
        "projected_landed_eo_gib": round(
            projected_bytes / 1024**3, 3),
        "hard_caps": caps,
        "cap_breaches": breaches,
        "no_support_weakening_rule": (
            "projection only; scientific support is never trimmed to "
            "fit a cap; any breach is an owner-review STOP"),
        "verdict": VERDICT_STOP if breaches else VERDICT_PROCEED,
    }
