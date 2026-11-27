"""SpartinaShift split construction and leakage auditing."""

from __future__ import annotations

from spartina.benchmark.splits.blocks import (
    SPLIT_ORDER,
    SPLIT_TARGETS,
    SplitRegion,
    choose_stripe_boundaries,
    component_crossings,
    make_regions,
)
from spartina.benchmark.splits.components import (
    ComponentInfo,
    crossing_component_ids,
    label_components,
)
from spartina.benchmark.splits.fingerprint import (
    logical_manifest_fingerprint,
    split_config_fingerprint,
)
from spartina.benchmark.splits.leakage import (
    AuditInputs,
    Violation,
    detect_boundary_and_guard,
    detect_component_cross_splits,
    detect_cross_split_pixel_overlap,
    detect_duplicates,
    detect_ignore_handling,
    detect_invalid_label_values,
    detect_metadata_consistency,
    detect_temporal_identity_duplicates,
    run_audit,
    violations_to_jsonable,
)

__all__ = [
    "AuditInputs",
    "ComponentInfo",
    "SPLIT_ORDER",
    "SPLIT_TARGETS",
    "SplitRegion",
    "Violation",
    "choose_stripe_boundaries",
    "component_crossings",
    "crossing_component_ids",
    "detect_boundary_and_guard",
    "detect_component_cross_splits",
    "detect_cross_split_pixel_overlap",
    "detect_duplicates",
    "detect_ignore_handling",
    "detect_invalid_label_values",
    "detect_metadata_consistency",
    "detect_temporal_identity_duplicates",
    "label_components",
    "logical_manifest_fingerprint",
    "make_regions",
    "run_audit",
    "split_config_fingerprint",
    "violations_to_jsonable",
]
