"""SpartinaShift-Silver v0.1 benchmark (Issue #20 Stage 1).

Phase A support inventory and Phase B frozen protocol logic. All label
supports are SILVER occupancy summaries; GOLD = 0; CM-SSM is external
reference only and never enters training, tuning or source selection.
"""

from spartina.benchmark.silver.support import (
    ACTUAL_MASK_GATE,
    ANALYSIS_GRID_M,
    RIGHTS_BY_SOURCE_KEY,
    SENSOR_INFO,
    build_support_matrix,
    task_support_summary,
)

__all__ = [
    "ACTUAL_MASK_GATE",
    "ANALYSIS_GRID_M",
    "RIGHTS_BY_SOURCE_KEY",
    "SENSOR_INFO",
    "build_support_matrix",
    "task_support_summary",
]
