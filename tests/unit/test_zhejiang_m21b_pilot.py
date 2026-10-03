"""Offline unit tests for the M2.1b Issue #13 pilot selection module.

Everything here is a pure function of in-memory fixtures: no GEE, no
Drive, no network, no tracked parquet. The frozen real-cell roster is
tested separately by tests/unit/test_zhejiang_artifacts.py.
"""

from __future__ import annotations

import pytest

from spartina.data.zhejiang.m21b_pilot import (
    COVERAGE_MIN,
    SCENE_CLOUD_MAX,
    STRATUM_DISAGREEMENT,
    STRATUM_HIGH_SILVER,
    STRATUM_LOW_SILVER,
    STRATUM_MEDIUM_SILVER,
    STRATUM_UNLABELED,
    STRATUM_VERY_LOW_SILVER,
    CellLabelSummary,
    SceneCoverage,
    evaluate_optical_group,
    first_eligible,
    first_s1_per_pass,
    pick_extra_multitile_event,
    pick_primary_s2_event,
    s1_db_audit,
    select_pilot_cells,
    summarize_cell_labels,
)


def _row(asset: str, tier: str, area: float, fraction: float = 0.0,
         status: str = "", bay_clip: float = 100.0) -> dict[str, object]:
    return {
        "cell_size_m": 10000,
        "asset_id": asset,
        "label_tier": tier,
        "positive_area_km2_bay_clip": area,
        "overlap_fraction_of_bay_clip": fraction,
        "cell_label_status_bay_scoped": status,
        "bay_clip_area_km2": bay_clip,
    }


def _summary(cid: str, *, silver: float = 0.0, weak: float = 0.0,
             coastal: str = "COASTAL_RELEVANT", bay_clip: float = 100.0,
             s2: bool = False) -> CellLabelSummary:
    # All six label assets always appear in the real overlap manifest,
    # including zero-area rows, so bay-clip area exists for unlabeled cells.
    weak_areas = (weak, weak * 1.5, 0.0, 0.0, 0.0)
    return summarize_cell_labels(
        cell_id=cid,
        overlap_rows=(
            [_row("L1", "SILVER", silver * bay_clip, silver,
                  "SILVER_POSITIVE" if silver > 0 else "",
                  bay_clip=bay_clip)]
            + [_row(f"L{i}", "WEAK", weak_value * bay_clip,
                    bay_clip=bay_clip)
               for i, weak_value in enumerate(weak_areas, start=2)]),
        coastal_relevance=coastal, s2_quality_event_in_v0_1=s2)


def _scene(sid: str, *, coverage: float, cloud: float | None = 0.01,
           utc: str = "2022-10-02T02:39:22+00:00", doy: int = 275,
           tile: str | None = "51RUP", datatake: str | None = "GS",
           pass_dir: str | None = None) -> SceneCoverage:
    return SceneCoverage(
        scene_id=sid, utc=utc, doy=doy, coverage_fraction=coverage,
        cloud_fraction=cloud, mgrs_tile=tile,
        datatake_identifier=datatake, pass_direction=pass_dir)


# ---------------------------------------------------------------------------
# label summaries
# ---------------------------------------------------------------------------

def test_weak_area_is_max_never_sum() -> None:
    s = _summary("C", weak=0.10)  # two WEAK products at 10 and 15 km2
    assert s.any_weak_positive
    assert s.weak_max_area_km2 == 15.0  # MAX, not 25.0


def test_unlabeled_requires_every_tier_absent() -> None:
    assert _summary("C").unlabeled
    assert not _summary("C", silver=0.01).unlabeled
    assert not _summary("C", weak=0.01).unlabeled


def test_non_10km_rows_ignored() -> None:
    s = summarize_cell_labels(
        cell_id="C", overlap_rows=[
            {"cell_size_m": 5000, "asset_id": "X", "label_tier": "SILVER",
             "positive_area_km2_bay_clip": 9.0,
             "overlap_fraction_of_bay_clip": 0.9,
             "bay_clip_area_km2": 10.0,
             "cell_label_status_bay_scoped": "SILVER_POSITIVE"}],
        coastal_relevance="COASTAL_RELEVANT",
        s2_quality_event_in_v0_1=False)
    assert not s.silver_positive
    assert s.unlabeled


# ---------------------------------------------------------------------------
# deterministic stratified selection
# ---------------------------------------------------------------------------

def _roster() -> dict[str, CellLabelSummary]:
    cells = {}
    # SILVER-positive fractions descending, lexical ids
    for i, frac in enumerate([0.40, 0.30, 0.20, 0.10, 0.001, 0.0005]):
        cid = f"E{i:02d}"
        # only the two smallest-positive cells carry a v0_1 S2 event
        cells[cid] = _summary(cid, silver=frac, s2=frac <= 0.001)
    # disagreement cells: SILVER-positive but OUTSIDE the top-4 ranks so
    # the diagnostic strata are not pre-empted by the fraction slots
    cells["D1"] = _summary("D1", silver=0.05, weak=0.05)
    cells["D2"] = _summary("D2", silver=0.04, weak=0.04)
    # unlabeled coastal controls with/without v0_1 event
    cells["U1"] = _summary("U1", bay_clip=80.0, s2=True)
    cells["U2"] = _summary("U2", bay_clip=90.0, s2=False)
    cells["U3"] = _summary("U3", bay_clip=95.0, s2=True,
                           coastal="INLAND_BUFFER")
    return cells


def test_selection_strata_order_and_determinism() -> None:
    roster = _roster()
    disagreement = {
        "D1": {"cell_id": "D1", "jaccard": 0.05,
               "silver_only_px": 100, "weak_only_px": 200},
        "D2": {"cell_id": "D2", "jaccard": 0.60,
               "silver_only_px": 10, "weak_only_px": 12},
        "E00": {"cell_id": "E00", "jaccard": 0.90,
                "silver_only_px": 1, "weak_only_px": 1}}
    first = select_pilot_cells(roster, disagreement)
    second = select_pilot_cells(roster, disagreement)
    assert [c.cell_id for c in first] == [c.cell_id for c in second]
    strata = [c.stratum for c in first]
    assert strata == [
        STRATUM_HIGH_SILVER,
        STRATUM_MEDIUM_SILVER, STRATUM_MEDIUM_SILVER,
        STRATUM_LOW_SILVER,
        STRATUM_DISAGREEMENT, STRATUM_DISAGREEMENT,
        STRATUM_VERY_LOW_SILVER, STRATUM_UNLABELED]
    # highest fraction wins HIGH
    assert first[0].cell_id == "E00" and first[0].rank_value == 0.40
    # lowest Jaccard diagnostic cell D1 fills the first disagreement slot
    assert first[4].cell_id == "D1"
    # second-lowest Jaccard excluding already-chosen D1
    assert first[5].cell_id == "D2"
    # very-low positive must have a v0_1 event: E04 (0.001) not E05? both
    # qualify; smallest fraction with s2 is E05
    assert first[6].cell_id == "E05"
    # control: largest bay-clip UNOBSERVED-relevant cell WITH v0_1 event;
    # U3 is inland-buffer (excluded), U2 lacks the event -> U1
    assert first[7].cell_id == "U1"
    assert 6 <= len(first) <= 8


def test_selection_never_duplicates_cells() -> None:
    roster = _roster()
    disagreement = {"E00": {"cell_id": "E00", "jaccard": 0.01,
                            "silver_only_px": 1, "weak_only_px": 1}}
    choices = select_pilot_cells(roster, disagreement)
    ids = [c.cell_id for c in choices]
    assert len(ids) == len(set(ids))
    # E00 already HIGH; disagreement slot goes to next-lowest or is empty
    assert all(c.cell_id != "E00" or c.stratum == STRATUM_HIGH_SILVER
               for c in choices)


def test_control_cell_is_unlabeled_not_negative() -> None:
    roster = _roster()
    choices = select_pilot_cells(roster, {})
    control = next(c for c in choices if c.stratum == STRATUM_UNLABELED)
    assert control.label.unlabeled
    assert "never NEGATIVE" in control.rationale


# ---------------------------------------------------------------------------
# event gating: R1 contributing semantics
# ---------------------------------------------------------------------------

def test_contributing_scene_is_any_intersection() -> None:
    # one sliver scene (0.001) plus a full-cover scene -> both contribute;
    # the sliver's cloud counts towards the contributing cloud maximum
    ev = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=[_scene("A", coverage=1.0, cloud=0.01),
                _scene("B", coverage=0.001, cloud=0.99)],
        union_coverage=1.0)
    assert ev.member_tiles
    assert ev.coverage_gate
    assert ev.cloud_gate == "FAIL"
    assert not ev.eligible
    assert ev.contributing_cloud_max == pytest.approx(0.99)


def test_union_coverage_gate_only() -> None:
    # individual scenes below 0.99 but the union passes
    ev = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=[_scene("A", coverage=0.60, cloud=0.02),
                _scene("B", coverage=0.45, cloud=0.03)],
        union_coverage=0.995)
    assert ev.coverage_gate and ev.eligible


def test_union_below_gate_fails_even_with_clear_scenes() -> None:
    ev = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=[_scene("A", coverage=0.5, cloud=0.0)],
        union_coverage=0.5)
    assert not ev.coverage_gate and not ev.eligible


def test_non_intersecting_scene_excluded_from_cloud_max() -> None:
    ev = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=[_scene("A", coverage=1.0, cloud=0.05),
                _scene("Z", coverage=0.0, cloud=0.99)],
        union_coverage=1.0)
    assert ev.eligible
    assert ev.contributing_cloud_max == pytest.approx(0.05)
    assert "Z" in ev.member_scene_ids  # recorded, but not contributing


def test_missing_cloud_metadata_fails_closed() -> None:
    ev = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=[_scene("A", coverage=1.0, cloud=None)],
        union_coverage=1.0)
    assert ev.cloud_gate == "MISSING_CLOUD_METADATA"
    assert not ev.eligible


def test_multitile_detection_and_determinism() -> None:
    scenes = [
        _scene("20221010T..._T51RUP", coverage=0.7, tile="51RUP"),
        _scene("20221010T..._T51RTP", coverage=0.5, tile="51RTP")]
    ev1 = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=scenes, union_coverage=1.0)
    ev2 = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="G",
        scenes=list(reversed(scenes)), union_coverage=1.0)
    assert ev1.multi_tile and ev1.member_tiles == ("51RTP", "51RUP")
    assert ev1 == ev2


def test_primary_clearest_then_earliest() -> None:
    a = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="A",
        scenes=[_scene("A", coverage=1.0, cloud=0.20,
                       utc="2022-10-02T02:39:22+00:00")],
        union_coverage=1.0)
    b = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="B",
        scenes=[_scene("B", coverage=1.0, cloud=0.05,
                       utc="2022-10-10T02:49:24+00:00")],
        union_coverage=1.0)
    assert pick_primary_s2_event([a, b]).event_key == "B"
    assert pick_primary_s2_event([a]) is a
    assert pick_primary_s2_event([]) is None


def test_extra_multitile_excludes_primary_key() -> None:
    single = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="S",
        scenes=[_scene("S", coverage=1.0, cloud=0.01)],
        union_coverage=1.0)
    assert pick_extra_multitile_event([single], set()) is None
    multi = evaluate_optical_group(
        cell_id="C", sensor="sentinel2", group_key="M",
        scenes=[_scene("M1", coverage=0.7, tile="51RUP"),
                _scene("M2", coverage=0.6, tile="51RUQ")],
        union_coverage=1.0)
    assert pick_extra_multitile_event(
        [single, multi], {"M"}) is None
    assert pick_extra_multitile_event(
        [single, multi], {"S"}).event_key == "M"


# ---------------------------------------------------------------------------
# Landsat / S1 first-eligible rules
# ---------------------------------------------------------------------------

def test_first_eligible_earliest_cloud_and_coverage() -> None:
    scenes = [
        _scene("EARLY_CLOUDY", coverage=1.0, cloud=0.5,
               utc="2022-09-20T02:00:00+00:00"),
        _scene("MID", coverage=1.0, cloud=0.25,
               utc="2022-09-25T02:00:00+00:00"),
        _scene("LATE", coverage=1.0, cloud=0.01,
               utc="2022-10-01T02:00:00+00:00"),
        _scene("PARTIAL", coverage=0.5, cloud=0.0,
               utc="2022-09-22T02:00:00+00:00")]
    # only MID and LATE pass both gates; earliest is MID (0.25 <= cap)
    assert first_eligible(scenes).scene_id == "MID"
    assert SCENE_CLOUD_MAX >= 0.25
    assert first_eligible(scenes[:1] + scenes[3:]) is None


def test_first_s1_pass_separation() -> None:
    scenes = [
        _scene("ASC_LATE", coverage=1.0, cloud=None,
               utc="2022-10-05T09:55:00+00:00", pass_dir="ASCENDING",
               tile=None),
        _scene("ASC_EARLY", coverage=1.0, cloud=None,
               utc="2022-09-17T09:55:00+00:00", pass_dir="ASCENDING",
               tile=None),
        _scene("DESC", coverage=1.0, cloud=None,
               utc="2022-09-25T21:00:00+00:00", pass_dir="DESCENDING",
               tile=None),
        _scene("DESC_PARTIAL", coverage=0.4, cloud=None,
               utc="2022-09-20T21:00:00+00:00", pass_dir="DESCENDING",
               tile=None)]
    picks = first_s1_per_pass(scenes)
    assert set(picks) == {"ASCENDING", "DESCENDING"}
    assert picks["ASCENDING"].scene_id == "ASC_EARLY"
    assert picks["DESCENDING"].scene_id == "DESC"


def test_first_s1_missing_pass_absent_from_dict() -> None:
    only_asc = [_scene("A", coverage=COVERAGE_MIN, cloud=None,
                       pass_dir="ASCENDING", tile=None)]
    assert set(first_s1_per_pass(only_asc)) == {"ASCENDING"}


# ---------------------------------------------------------------------------
# S1 dB identity audit (envelope only; the driver adds server recompute)
# ---------------------------------------------------------------------------

def _stats(vv: tuple[float, float], vh: tuple[float, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for band, (lo, hi) in (("VV", vv), ("VH", vh)):
        out.update({f"{band}_min": lo, f"{band}_p01": lo + 1,
                    f"{band}_p50": (lo + hi) / 2,
                    f"{band}_p99": hi - 1, f"{band}_max": hi})
    return out


def test_s1_db_audit_accepts_observed_db() -> None:
    audit = s1_db_audit(_stats((-39.9, 22.3), (-43.9, 13.3)))
    assert audit["pass"]
    assert audit["transform_applied"] == "IDENTITY_SELECT_ONLY_NO_10LOG10"


def test_s1_db_audit_rejects_double_log_values() -> None:
    audit = s1_db_audit(_stats((-220.0, -60.0), (-230.0, -70.0)))
    assert not audit["pass"]


def test_s1_db_audit_rejects_absurd_positive() -> None:
    audit = s1_db_audit(_stats((-20.0, 80.0), (-25.0, 40.0)))
    assert not audit["pass"]
