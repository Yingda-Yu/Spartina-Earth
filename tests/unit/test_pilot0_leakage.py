"""Step 11/12: hard-fail leakage audit, including deliberately broken
synthetic fixtures. Every fixture MUST make the audit FAIL with the
expected violation code; the clean baseline MUST pass."""

from __future__ import annotations

from spartina.benchmark.splits.leakage import AuditInputs, run_audit

PATCH = 96
GUARD = 48
CHECKSUM = "0" * 64
CRS = "EPSG:32651"
TRANSFORM = (30.0, 0.0, 309290.0, 0.0, -30.0, 3364370.0)
# owners: train [0,448), val [448,848), test [848,1300); usable interiors
REGIONS = {"train": (0, 400), "val": (496, 800), "test": (896, 1300)}

FRACTIONS = (
    "silver_fraction", "weak_fraction", "ignore_fraction",
    "weak_only_candidate_fraction", "optical_valid_fraction",
    "sar_valid_fraction", "vv_valid_fraction", "vh_valid_fraction",
    "indices_valid_fraction",
)
COUNTS = ("silver_positive_pixels", "weak_positive_pixels",
          "ignore_pixels", "weak_only_candidate_pixels")


def _record(tid: str, split: str, r0: int, c0: int) -> dict:
    r = {
        "tile_id": tid, "split": split,
        "row_off": r0, "col_off": c0, "height": PATCH, "width": PATCH,
        "source_stack_checksum": CHECKSUM, "source_crs": CRS,
        "source_transform": list(TRANSFORM),
        "silver_eval_pixels": 0, "weak_eval_pixels": 0,
        "silver_component_ids": [], "weak_candidate_component_ids": [],
    }
    for f in FRACTIONS:
        r[f] = 0.0
    for f in COUNTS:
        r[f] = 0
    return r


def _baseline() -> list[dict]:
    out = []
    for split, (lo, hi) in REGIONS.items():
        for c0 in (lo, (lo + hi) // 2):
            for r0 in (0, 96):
                out.append(_record(
                    f"HB2015_R{r0:04d}_C{c0:04d}_P{PATCH:03d}",
                    split, r0, c0))
    return out


def _audit(records: list[dict]) -> list:
    return run_audit(AuditInputs(
        records=records, regions=dict(REGIONS), guard_px=GUARD,
        expected_stack_checksum=CHECKSUM, expected_crs=CRS,
        expected_transform=TRANSFORM, patch=PATCH))


def _codes(violations: list) -> set[str]:
    return {v.code for v in violations}


# ---------------------------------------------------------------- clean --

def test_clean_baseline_passes() -> None:
    assert _audit(_baseline()) == []


# ------------------------------------------------------- fault fixtures --

def test_fixture_overlap_pixels_fails() -> None:
    recs = _baseline()
    bad = _record("HB2015_R0000_C0050_P096", "test", 0, 50)
    recs.append(bad)  # shares source pixels with train window at c0=0
    codes = _codes(_audit(recs))
    assert "SHARED_SOURCE_PIXEL" in codes


def test_fixture_same_component_two_splits_fails() -> None:
    recs = _baseline()
    recs[0]["silver_component_ids"] = ["silver-0009"]
    recs[-1]["silver_component_ids"] = ["silver-0009"]
    codes = _codes(_audit(recs))
    assert "SILVER_COMPONENT_IN_MULTIPLE_SPLITS" in codes
    # weak variant
    recs = _baseline()
    recs[0]["weak_candidate_component_ids"] = ["weakcand-0003"]
    recs[-1]["weak_candidate_component_ids"] = ["weakcand-0003"]
    assert "WEAK_COMPONENT_IN_MULTIPLE_SPLITS" in _codes(_audit(recs))


def test_fixture_guard_violation_fails() -> None:
    recs = _baseline()
    # train window reaches into the 48 px guard zone (ends at col 456)
    recs.append(_record("HB2015_R0000_C0360_P096", "train", 0, 360))
    codes = _codes(_audit(recs))
    assert "INSUFFICIENT_GUARD_DISTANCE" in codes


def test_fixture_duplicate_tile_id_fails() -> None:
    recs = _baseline()
    dup = dict(recs[0])
    dup["col_off"] = 250
    recs.append(dup)
    codes = _codes(_audit(recs))
    assert "DUPLICATE_TILE_ID" in codes


def test_fixture_duplicate_source_window_fails() -> None:
    recs = _baseline()
    dup = dict(recs[0])
    dup["tile_id"] = "HB2015_R0000_C0000_P064"
    recs.append(dup)
    codes = _codes(_audit(recs))
    assert "DUPLICATE_SOURCE_WINDOW" in codes


def test_fixture_wrong_checksum_fails() -> None:
    recs = _baseline()
    recs[0]["source_stack_checksum"] = "f" * 64
    codes = _codes(_audit(recs))
    assert "MANIFEST_CHECKSUM_MISMATCH" in codes


def test_fixture_wrong_crs_and_transform_fail() -> None:
    recs = _baseline()
    recs[0]["source_crs"] = "EPSG:32650"
    codes = _codes(_audit(recs))
    assert "INCONSISTENT_CRS" in codes
    recs = _baseline()
    bad_t = list(TRANSFORM)
    bad_t[2] += 30.0
    recs[0]["source_transform"] = bad_t
    assert "INCONSISTENT_TRANSFORM" in _codes(_audit(recs))


def test_fixture_cross_boundary_window_fails() -> None:
    recs = _baseline()
    recs.append(_record("HB2015_R0000_C0400_P096", "val", 0, 400))
    codes = _codes(_audit(recs))
    assert "WINDOW_CROSSES_SPLIT_BOUNDARY" in codes


def test_fixture_invalid_label_and_ignore_failures() -> None:
    recs = _baseline()
    recs[0]["silver_fraction"] = 1.5
    assert "INVALID_LABEL_VALUES" in _codes(_audit(recs))
    recs = _baseline()
    recs[0]["silver_positive_pixels"] = 10
    recs[0]["silver_eval_pixels"] = 11
    assert "IGNORE_HANDLING_ERROR" in _codes(_audit(recs))


def test_fixture_temporal_identity_duplicate_fails() -> None:
    recs = _baseline()
    recs[0]["temporal_identity"] = ["HB2015", 12, 120, 2015, "L8"]
    recs[-1]["temporal_identity"] = ["HB2015", 12, 120, 2015, "L8"]
    codes = _codes(_audit(recs))
    assert "TEMPORAL_IDENTITY_DUPLIC" in "".join(codes)
