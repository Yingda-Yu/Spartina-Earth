"""Safety invariants for the national metadata census (no exports, etc.)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from spartina.data.zhejiang.census import ExportAttempted, install_export_guard

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts" / "data" / "national"


def test_export_guard_blocks_and_restores() -> None:
    fake_ee = SimpleNamespace(batch=SimpleNamespace(Export=object()))
    restore = install_export_guard(fake_ee)
    with pytest.raises(ExportAttempted):
        fake_ee.batch.Export.table.toDrive(**{"x": 1})  # type: ignore[attr-defined]
    with pytest.raises(ExportAttempted):
        fake_ee.batch.Export.image.toCloudStorage(  # type: ignore[attr-defined]
            **{"x": 1}
        )
    restore()
    assert not isinstance(fake_ee.batch.Export, type) or isinstance(
        fake_ee.batch.Export, object
    )


def test_fetch_scripts_install_guard_and_never_export() -> None:
    for name in ("fetch_optical_census.py", "fetch_s1_geometry_census.py"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "install_export_guard(ee)" in text
        # The blocked sentinel is the only Export reference allowed.
        assert "Export." not in text.replace("ee.batch.Export is forbidden", "")


def test_s1_fetches_passes_separately() -> None:
    text = (SCRIPTS / "fetch_s1_geometry_census.py").read_text(encoding="utf-8")
    assert '("ASC", "ASCENDING"), ("DESC", "DESCENDING")' in text
    assert "ASC and DESC always separate calls" in text
    # Half-year fallback keeps passes separate too.
    assert "YEAR_BATCH_FAILED_SPLIT" in text
