"""Schema/content guard for the Issue #7 Zhejiang availability matrix."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "scripts" / "data" / "zhejiang" / "availability_matrix.py"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("availability_matrix", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_matrix_shape_and_unknown_discipline() -> None:
    module = _load_module()
    rows = module.build_rows()
    # 1985 + 1990..2026 = 38 years, three bays
    assert len(rows) == 38 * 3
    years = sorted({int(row["year"]) for row in rows})
    assert years[0] == 1985 and years[1] == 1990 and years[-1] == 2026

    for row in rows:
        assert set(row) == set(module.COLUMNS)
        # No fabricated evidence in v0: ROI scene counts and labels
        # remain MISSING until the GEE factory populates a new version.
        assert row["landsat_roi_scene_count"] == "MISSING"
        assert row["sentinel1_roi_scene_count"] == "MISSING"
        assert row["sentinel2_roi_scene_count"] == "MISSING"
        assert row["label_available"] == "MISSING"
        assert row["field_uav_available"] == "MISSING"
        assert row["tide_metadata"] == "MISSING"
        assert row["status"] == "NOT_ASSESSED"


def test_mission_eras_are_marked_conservatively() -> None:
    module = _load_module()
    rows = module.build_rows()
    by_year_region = {(int(r["year"]), r["roi_id"]): r for r in rows}
    hzb_2003 = by_year_region[(2003, "ZJ-HZB")]
    assert "SLC_OFF" in hzb_2003["landsat_sensor_nominal"]
    assert by_year_region[(2013, "ZJ-HZB")]["landsat_sensor_nominal"].count(
        "LANDSAT8")
    assert by_year_region[(2022, "ZJ-HZB")]["landsat_sensor_nominal"].count(
        "LANDSAT9")
    assert by_year_region[(2010, "ZJ-HZB")]["sentinel1_nominal"] == "MISSING"
    assert "SR_HARMONIZED" in by_year_region[
        (2020, "ZJ-HZB")]["sentinel2_nominal"]


def test_writer_roundtrip(tmp_path: Path) -> None:
    module = _load_module()
    out = module.write_matrix(tmp_path / "matrix.csv")
    assert out.read_text(encoding="utf-8").startswith("year,roi_id,region,")
