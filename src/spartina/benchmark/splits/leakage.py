"""Hard-fail leakage audit for split window manifests (Issue #4).

Every detector returns :class:`Violation` objects; an empty list means
PASS. The audit deliberately works on plain records (dicts) plus the
split regions so it can be reused by synthetic-fixture tests and on
future windows without raster dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np

from spartina.data.tiling.windows import WindowSpec


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str
    tile_ids: tuple[str, ...] = ()


@dataclass
class AuditInputs:
    """Everything the audit needs, independent of rasters."""

    records: list[dict[str, Any]]
    regions: dict[str, tuple[int, int]]  # usable (start, end) columns
    guard_px: int
    expected_stack_checksum: str
    expected_crs: str
    expected_transform: tuple[float, ...]
    patch: int
    label_arrays: dict[str, Any] | None = None  # silver/weak/ignore uint masks


# --------------------------------------------------------------------------
# individual detectors
# --------------------------------------------------------------------------

def _spec(r: dict[str, Any]) -> WindowSpec:
    return WindowSpec(int(r["row_off"]), int(r["col_off"]),
                      int(r["height"]), int(r["width"]))


def detect_cross_split_pixel_overlap(
    records: list[dict[str, Any]],
) -> list[Violation]:
    """Shared source pixels between windows assigned different splits."""
    out: list[Violation] = []
    active = [r for r in records if r.get("split") in {"train", "val", "test"}]
    for i, a in enumerate(active):
        sa, wa = _spec(a), a["split"]
        for b in active[i + 1:]:
            if b["split"] == wa:
                continue
            if sa.shares_pixels(_spec(b)):
                out.append(Violation(
                    "SHARED_SOURCE_PIXEL",
                    f"{wa} window {a['tile_id']} shares pixels with "
                    f"{b['split']} window {b['tile_id']}",
                    (a["tile_id"], b["tile_id"]),
                ))
    return out


def detect_boundary_and_guard(
    records: list[dict[str, Any]], regions: dict[str, tuple[int, int]],
    guard_px: int,
) -> list[Violation]:
    """Window crosses its split interior or enters a guard zone."""
    out: list[Violation] = []
    for r in records:
        split = r.get("split")
        if split not in regions:
            continue
        lo, hi = regions[split]
        c0, c1 = int(r["col_off"]), int(r["col_off"]) + int(r["width"])
        if c0 < lo or c1 > hi:
            out.append(Violation(
                "WINDOW_CROSSES_SPLIT_BOUNDARY",
                f"{r['tile_id']} columns [{c0},{c1}) leave {split} usable "
                f"interior [{lo},{hi})",
                (r["tile_id"],),
            ))
        # guard distance to the *ownership* boundary of any other split
        order = ("train", "val", "test")
        idx = order.index(split)
        other_lines = []
        if idx > 0:
            other_lines.append(regions[order[idx - 1]][1] + guard_px)
        if idx < 2:
            other_lines.append(regions[order[idx + 1]][0] - guard_px)
        for line in other_lines:
            gap = min(abs(c0 - line), abs(c1 - line))
            if gap < guard_px:
                out.append(Violation(
                    "INSUFFICIENT_GUARD_DISTANCE",
                    f"{r['tile_id']} is {gap} px from split boundary "
                    f"(required >= {guard_px})",
                    (r["tile_id"],),
                ))
    return out


def detect_component_cross_splits(
    records: list[dict[str, Any]], id_field: str, code: str
) -> list[Violation]:
    """A connected component appears in windows of multiple splits."""
    seen: dict[str, set[str]] = {}
    owners: dict[str, str] = {}
    for r in records:
        split = r.get("split")
        if split not in {"train", "val", "test"}:
            continue
        for cid in r.get(id_field, ()):
            seen.setdefault(cid, set()).add(split)
            owners.setdefault(cid, r["tile_id"])
    return [
        Violation(
            code,
            f"component {cid} present in splits {sorted(splits)}",
            (owners[cid],),
        )
        for cid, splits in seen.items()
        if len(splits) > 1
    ]


def detect_duplicates(records: list[dict[str, Any]]) -> list[Violation]:
    """Duplicate tile IDs and duplicate source windows."""
    out: list[Violation] = []
    ids: dict[str, str] = {}
    geoms: dict[tuple[int, ...], str] = {}
    for r in records:
        tid = r["tile_id"]
        if tid in ids:
            out.append(Violation(
                "DUPLICATE_TILE_ID", f"tile_id repeated: {tid}", (tid,)))
        ids[tid] = tid
        geom = (int(r["row_off"]), int(r["col_off"]),
                int(r["height"]), int(r["width"]))
        if geom in geoms:
            out.append(Violation(
                "DUPLICATE_SOURCE_WINDOW",
                f"window {geom} duplicated ({geoms[geom]}, {tid})",
                (geoms[geom], tid),
            ))
        geoms[geom] = tid
    return out


def detect_metadata_consistency(
    records: list[dict[str, Any]], inputs: AuditInputs
) -> list[Violation]:
    """CRS / transform / checksum consistency against the contract."""
    out: list[Violation] = []
    for r in records:
        if r.get("source_stack_checksum") != inputs.expected_stack_checksum:
            out.append(Violation(
                "MANIFEST_CHECKSUM_MISMATCH",
                f"{r['tile_id']} checksum {r.get('source_stack_checksum')} "
                f"!= {inputs.expected_stack_checksum}",
                (r["tile_id"],),
            ))
        if r.get("source_crs") != inputs.expected_crs:
            out.append(Violation(
                "INCONSISTENT_CRS",
                f"{r['tile_id']} crs {r.get('source_crs')!r} "
                f"!= {inputs.expected_crs!r}",
                (r["tile_id"],),
            ))
        if tuple(r.get("source_transform", ())) != inputs.expected_transform:
            out.append(Violation(
                "INCONSISTENT_TRANSFORM",
                f"{r['tile_id']} transform mismatch", (r["tile_id"],),
            ))
    return out


def detect_invalid_label_values(inputs: AuditInputs) -> list[Violation]:
    """Label layers must be binary; ignore fractions must be valid."""
    out: list[Violation] = []
    arr = inputs.label_arrays
    if arr:
        for name in ("silver", "weak", "ignore"):
            a = arr.get(name)
            if a is not None and bool(np.setdiff1d(np.unique(a), [0, 1]).size):
                out.append(Violation(
                    "INVALID_LABEL_VALUES",
                    f"{name} layer has values outside {{0,1}}"))
    for r in inputs.records:
        n = int(r["height"]) * int(r["width"])
        for frac_field in ("silver_fraction", "weak_fraction",
                           "ignore_fraction",
                           "weak_only_candidate_fraction",
                           "optical_valid_fraction", "sar_valid_fraction",
                           "vv_valid_fraction", "vh_valid_fraction",
                           "indices_valid_fraction"):
            v = r.get(frac_field)
            if v is not None and not 0.0 <= float(v) <= 1.0 + 1e-9:
                out.append(Violation(
                    "INVALID_LABEL_VALUES",
                    f"{r['tile_id']} {frac_field}={v} outside [0,1]",
                    (r["tile_id"],),
                ))
        for count_field in ("silver_positive_pixels", "weak_positive_pixels",
                            "ignore_pixels",
                            "weak_only_candidate_pixels"):
            v = r.get(count_field)
            if v is not None and not 0 <= int(v) <= n:
                out.append(Violation(
                    "INVALID_LABEL_VALUES",
                    f"{r['tile_id']} {count_field}={v} outside [0,{n}]",
                    (r["tile_id"],),
                ))
    return out


def detect_ignore_handling(records: list[dict[str, Any]]) -> list[Violation]:
    """IGNORE pixels must never be counted as eval positives."""
    out: list[Violation] = []
    for r in records:
        n = int(r["height"]) * int(r["width"])
        ig = int(r.get("ignore_pixels", 0))
        if int(r.get("silver_positive_pixels", 0)) + ig > n + 0:
            pass  # silver may coincide with ignore; checked via eval count
        eval_s = int(r.get("silver_eval_pixels", -1))
        raw_s = int(r.get("silver_positive_pixels", 0))
        if eval_s < 0 or eval_s > raw_s:
            out.append(Violation(
                "IGNORE_HANDLING_ERROR",
                f"{r['tile_id']} silver_eval_pixels={eval_s} must be in "
                f"[0, silver_positive={raw_s}]",
                (r["tile_id"],),
            ))
        if int(r.get("weak_eval_pixels", 0)) > int(
                r.get("weak_positive_pixels", 0)):
            out.append(Violation(
                "IGNORE_HANDLING_ERROR",
                f"{r['tile_id']} weak eval count exceeds raw count",
                (r["tile_id"],),
            ))
    return out


def detect_temporal_identity_duplicates(
    records: list[dict[str, Any]],
) -> list[Violation]:
    """Future-proof check: same location+year+sensor must not collide.

    Pilot-0 has no temporal records; if ``temporal_identity`` is present
    it must be unique.
    """
    seen: dict[tuple[Any, ...], str] = {}
    out: list[Violation] = []
    for r in records:
        key = r.get("temporal_identity")
        if key is None:
            continue
        t = tuple(key)
        if t in seen:
            out.append(Violation(
                "TEMPORAL_IDENTITY_DUPLICATE",
                f"{t} repeated by {r['tile_id']} and {seen[t]}",
                (seen[t], r["tile_id"]),
            ))
        seen[t] = r["tile_id"]
    return out


def run_audit(inputs: AuditInputs) -> list[Violation]:
    """Run every hard-fail detector; return all violations."""
    records = inputs.records
    out: list[Violation] = []
    out += detect_cross_split_pixel_overlap(records)
    out += detect_boundary_and_guard(records, inputs.regions, inputs.guard_px)
    out += detect_component_cross_splits(
        records, "silver_component_ids", "SILVER_COMPONENT_IN_MULTIPLE_SPLITS")
    out += detect_component_cross_splits(
        records, "weak_candidate_component_ids",
        "WEAK_COMPONENT_IN_MULTIPLE_SPLITS")
    out += detect_duplicates(records)
    out += detect_metadata_consistency(records, inputs)
    out += detect_invalid_label_values(inputs)
    out += detect_ignore_handling(records)
    out += detect_temporal_identity_duplicates(records)
    return out


def violations_to_jsonable(
    violations: Iterable[Violation],
) -> list[dict[str, str | tuple[str, ...]]]:
    return [{"code": v.code, "detail": v.detail, "tile_ids": v.tile_ids}
            for v in violations]
