"""Tests for the stdlib-only audit tools: transfer detection + manifest."""

from __future__ import annotations

import json
from pathlib import Path

import build_asset_manifest as bam
import detect_transfer_state as dts
import freeze_dataset as fd


def _write(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_scan_and_compare_stable(tmp_path: Path) -> None:
    _write(tmp_path / "a.tif", b"AAAA")
    s1 = dts.scan_tree(tmp_path)
    s2 = dts.scan_tree(tmp_path)
    report = dts.compare_snapshots(s1, s2)
    assert report["overall_status"] == dts.STABLE
    assert report["counts"][dts.STABLE] == 1


def test_compare_detects_size_change_new_and_disappeared(tmp_path: Path) -> None:
    _write(tmp_path / "a.tif", b"AAAA")
    s1 = dts.scan_tree(tmp_path)
    (tmp_path / "a.tif").write_bytes(b"AAAAXXXX")  # size change
    _write(tmp_path / "b.tif", b"new")  # appeared after scan 1
    s2 = dts.scan_tree(tmp_path)
    report = dts.compare_snapshots(s1, s2)
    statuses = {f["relative_path"]: f["transfer_status"] for f in report["files"]}
    assert statuses["a.tif"] == dts.IN_PROGRESS
    assert statuses["b.tif"] == dts.IN_PROGRESS
    assert report["overall_status"] == dts.IN_PROGRESS

    s3 = dts.scan_tree(tmp_path)
    (tmp_path / "b.tif").unlink()
    s4 = dts.scan_tree(tmp_path)
    report2 = dts.compare_snapshots(s3, s4)
    assert any(f["transfer_status"] == dts.DISAPPEARED for f in report2["files"])


def test_asset_classification_compound_suffixes() -> None:
    assert bam.classify("CM-SSM.shp.xml")[0] == "shapefile_metadata_xml"
    assert bam.classify("x.tif.vat.dbf")[0] == "raster_vat_dbf"
    assert bam.classify("x.aux.xml")[0] == "gdal_aux_xml"
    assert bam.classify("S2_2019.TIF")[0] == "geotiff"
    assert bam.classify("notes.tar.gz")[0] == "archive_tar_gz"
    assert bam.classify("README.unknown")[0] == "other"


def test_sha256_known_vector(tmp_path: Path) -> None:
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    # SHA-256 of b"abc"
    assert bam.sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_build_rows_hashes_only_stable_and_flags_duplicates(tmp_path: Path) -> None:
    _write(tmp_path / "stable_a.bin", b"same-bytes")
    _write(tmp_path / "stable_b.bin", b"same-bytes")
    _write(tmp_path / "pending.bin", b"changing")
    statuses = {
        "stable_a.bin": dts.STABLE,
        "stable_b.bin": dts.STABLE,
        "pending.bin": dts.IN_PROGRESS,
    }
    rows = bam.build_rows(tmp_path, statuses, do_hash=True)
    by_name = {Path(r["relative_path"]).name: r for r in rows}
    assert by_name["stable_a.bin"]["sha256"] is not None
    assert by_name["stable_a.bin"]["transfer_status"] == "STABLE_CANDIDATE"
    assert by_name["pending.bin"]["sha256"] is None
    assert by_name["pending.bin"]["transfer_status"] == "PENDING_TRANSFER"
    # identical stable files share an asset_id
    assert by_name["stable_a.bin"]["asset_id"] == by_name["stable_b.bin"]["asset_id"]
    assert "byte-identical duplicate" in by_name["stable_b.bin"]["known_issues"]


def test_manifest_columns_are_complete() -> None:
    for col in ("asset_id", "sha256", "transfer_status", "asset_type", "label_quality", "license"):
        assert col in bam.COLUMNS


def test_freeze_refuses_without_owner_flag(tmp_path: Path) -> None:
    rc = fd.main(["--root", str(tmp_path)])
    assert rc == 2


def test_freeze_refuses_on_unstable_state(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"overall_status": "IN_PROGRESS", "files": []}))
    rc = fd.main(
        [
            "--root", str(tmp_path),
            "--transfer-state", str(state),
            "--owner-confirmed-transfer-complete",
        ]
    )
    assert rc == 2
