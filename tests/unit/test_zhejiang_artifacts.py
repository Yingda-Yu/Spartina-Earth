"""Consistency of the committed Zhejiang M2.1a manifest artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import shape

from spartina.data.gee.selection import canonical_fingerprint
from spartina.data.zhejiang.contracts import (
    CENSUS_SUMMARY_COLUMNS,
    GAP_NOT_OPERATIONAL,
    GAP_STATUSES,
    LABEL_INVENTORY_COLUMNS,
    ROI_REGISTRY_COLUMNS,
    SENSORS,
)
from spartina.data.zhejiang.rois import geometry_fingerprint

ROOT = Path(__file__).resolve().parents[2]
MAN = ROOT / "datasets/manifests"
ROIS_GJ = ROOT / "datasets/rois/zhejiang_bays_v0.geojson"


NULLABLE_INT_COLUMNS = {
    "scene_cloud_eligible_scenes", "footprint_coverage_eligible_scenes",
    "season_candidate_scenes", "quality_candidate_scenes",
}
# label overlap columns were fingerprinted as int counts for label assets
# and as descriptive strings for footprint-only composites; parquet stores
# the whole object column as string
OVERLAP_INT_COLUMNS = {"overlap_zj_hzb", "overlap_zj_smb",
                       "overlap_zj_yqb"}


def _clean(row):
    """parquet/arrow returns numpy scalars and NaN; builders fingerprinted
    plain Python values, so reproduce int-vs-float semantics per column."""
    out = {}
    for k, v in dict(row).items():
        if pd.isna(v):
            out[k] = None
        elif hasattr(v, "item"):
            out[k] = v.item()
        else:
            out[k] = v
        if k in NULLABLE_INT_COLUMNS and isinstance(out[k], float):
            out[k] = int(out[k])
        if k in OVERLAP_INT_COLUMNS and isinstance(out[k], str) \
                and out[k].isdigit():
            out[k] = int(out[k])
    return out


def test_roi_registry_and_geojson_agree():
    csv_df = pd.read_csv(MAN / "zhejiang_roi_registry_v0.csv")
    pq_df = pd.read_parquet(MAN / "zhejiang_roi_registry_v0.parquet")
    assert list(csv_df.columns) == list(ROI_REGISTRY_COLUMNS)
    assert csv_df.roi_id.tolist() == ["ZJ-HZB", "ZJ-SMB", "ZJ-YQB"]
    assert len(pq_df) == 3 and csv_df.roi_id.is_unique
    fc = json.loads(ROIS_GJ.read_text(encoding="utf-8"))
    assert len(fc["features"]) == 3
    gj_fp = {f["properties"]["roi_id"]:
             geometry_fingerprint(shape(f["geometry"]))
             for f in fc["features"]}
    for _, row in pq_df.iterrows():
        assert row["geometry_status"] == "PROVISIONAL_TIER_C_DERIVED"
        assert row["provenance_tier"] == "C_DERIVED"
        assert bool(row["geometry_is_valid"]) is True
        assert row["geometry_fingerprint"] == gj_fp[row["roi_id"]]
        payload = {k: v for k, v in _clean(row).items()
                   if k in ROI_REGISTRY_COLUMNS and k != "logical_fingerprint"}
        assert row["logical_fingerprint"] == canonical_fingerprint(payload)


def test_source_audit_covers_registry_evidence_ids():
    audit = pd.read_csv(MAN / "zhejiang_roi_source_audit_v0.csv")
    registry = pd.read_csv(MAN / "zhejiang_roi_registry_v0.csv")
    known = set(audit.source_id)
    for refs in registry["source_ids"]:
        for sid in str(refs).split("|"):
            sid = sid.strip()
            if sid and sid != "UNKNOWN":
                assert sid in known


def test_label_inventory_fingerprints_and_measured_overlaps():
    df = pd.read_parquet(MAN / "zhejiang_legacy_label_inventory_v0.parquet")
    assert list(df.columns) == list(LABEL_INVENTORY_COLUMNS)
    assert df.asset_id.is_unique
    assert set(df.label_tier) <= {"GOLD", "SILVER", "WEAK", "UNLABELED"}
    assert "GOLD" not in set(df.label_tier)
    for _, row in df.iterrows():
        payload = {k: v for k, v in _clean(row).items()
                   if k in LABEL_INVENTORY_COLUMNS and k != "logical_fingerprint"}
        assert row["logical_fingerprint"] == canonical_fingerprint(payload)
        assert "NO_GOLD_CANDIDATE_AT_M21A" in row["gold_candidate_issue"]
    # regression checks on the measured (not guessed) intersections
    assert (df.asset_id == "L1-china2015-raster30m").sum() == 1


def _overlap(df, asset_id, bay_col):
    rows = df[df.asset_id == asset_id]
    assert len(rows) == 1
    return rows.iloc[0][bay_col]


def test_label_measured_counts_regression():
    df = pd.read_parquet(MAN / "zhejiang_legacy_label_inventory_v0.parquet")
    assert int(_overlap(df, "L1-china2015-raster30m",
                        "overlap_zj_hzb")) == 19268
    assert int(_overlap(df, "L1-china2015-raster30m",
                        "overlap_zj_smb")) == 0
    assert int(_overlap(df, "L1-china2015-raster30m",
                        "overlap_zj_yqb")) == 22889
    assert int(_overlap(df, "L3-hangzhou-mask-2015",
                        "overlap_zj_hzb")) == 15600
    assert int(_overlap(df, "L5-cmsa-polygons-2020",
                        "overlap_zj_yqb")) == 158
    assert int(_overlap(df, "L2-cmssm2020-polygons",
                        "overlap_zj_hzb")) == 0


def test_census_summary_schema_and_era_matrix():
    df = pd.read_parquet(MAN / "zhejiang_eo_census_summary_v0.parquet")
    assert list(df.columns) == list(CENSUS_SUMMARY_COLUMNS)
    assert len(df) == 3 * 42 * 6
    assert set(df.gap_status) <= set(GAP_STATUSES)
    spans = {"landsat5": (1984, 2012), "landsat7": (1999, 2026),
             "landsat8": (2013, 2026), "landsat9": (2022, 2026),
             "sentinel1": (2014, 2026), "sentinel2": (2017, 2026)}
    for sensor, (a, b) in spans.items():
        pre = df[(df.sensor == sensor)
                 & ((df.year < a) | (df.year > b))]
        assert (pre.gap_status == GAP_NOT_OPERATIONAL).all()
        assert (pre.total_scenes == 0).all()
        during = df[(df.sensor == sensor)
                    & (df.year >= a) & (df.year <= b)]
        assert (during.operational).all()
        assert (during.query_status == "QUERIED").all()
    for _, row in df.iterrows():
        payload = {k: v for k, v in _clean(row).items()
                   if k in CENSUS_SUMMARY_COLUMNS and k != "summary_fingerprint"}
        assert row["summary_fingerprint"] == canonical_fingerprint(payload)
    # ROI pixel QA must never have run at M2.1a
    assert df.quality_candidate_scenes.isna().all()
    assert set(df.qa_level) == {"SCENE_METADATA"}
    # L7: pre/post SLC labels are both present and never blank
    l7 = df[(df.sensor == "landsat7") & (df.operational)]
    assert "POST_SLC_FAILURE" in set(l7.slc_status)


def test_availability_and_gap_matrices():
    avail = pd.read_csv(MAN / "zhejiang_eo_availability_v0.csv")
    gaps = pd.read_csv(MAN / "zhejiang_data_gap_matrix_v0.csv")
    assert len(avail) == 3 * 42
    assert avail.roi_id.isin(["ZJ-HZB", "ZJ-SMB", "ZJ-YQB"]).all()
    assert set(gaps.axis) >= set(SENSORS) | {"label", "field_uav",
                                             "management_event", "tide"}
    # no interpolation: every axis row carries an explicit status
    assert gaps.gap_status.notna().all()
    hzb2015 = avail[(avail.roi_id == "ZJ-HZB")
                    & (avail.year == 2015)].iloc[0]
    assert hzb2015.label_available in {"SILVER", "WEAK"}
    assert avail.field_uav_available.str.contains("NONE_FOUND").all()


def test_scene_table_manifest_nonempty_and_utc():
    p = MAN / "zhejiang_eo_scene_census_v0.parquet"
    assert p.exists()
    df = pd.read_parquet(p)
    assert len(df) > 0
    assert df.acquisition_utc.str.endswith("Z").all()
    ids = df.groupby(["roi_id", "sensor"]).scene_id.nunique()
    assert (ids > 0).all()
