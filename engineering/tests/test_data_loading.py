"""Data-loading tests (engineering/dataset_validation).

Round-trips a REAL landed product: manifest -> files -> rasterio open ->
grid/SHA verification. Uses the actual frozen export; skips (with reason)
if landed bytes are absent rather than fabricating a pass.
Run: pytest engineering/tests/test_data_loading.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np
import pytest
import rasterio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINEERING = os.path.join(ROOT, "engineering")
for p in (ROOT, ENGINEERING):
    if p not in sys.path:
        sys.path.insert(0, p)

INDEX = os.path.join(ROOT, "work/issue21/export/v02_export_index.json")
PRODUCTS_DIR = os.path.join(ROOT, "work/issue21/export/products")

pytestmark = pytest.mark.skipif(
    not os.path.exists(INDEX), reason="landed export index not present on this machine"
)


@pytest.fixture(scope="module")
def index():
    with open(INDEX) as f:
        return json.load(f)


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buf), b""):
            h.update(chunk)
    return h.hexdigest()


def find_landed_file(products_dir, product_id, token):
    prefix = f"spartina_v02_{product_id}"
    for fn in os.listdir(products_dir):
        if fn.startswith(prefix) and token in fn:
            return os.path.join(products_dir, fn)
    return None


def test_index_landed_counts(index):
    assert index["n_scope"] == index["n_landed"] == 722
    assert index["n_failures_open"] == 0
    assert len(index["products"]) == 722
    assert all(p["qa_gate_pass"] for p in index["products"])


def test_manifest_sha_roundtrip(index):
    """Manifest-listed sha256 matches recomputed sha for sample products."""
    products = index["products"][:5]
    checked = 0
    for p in products:
        with open(os.path.join(ROOT, p["manifest"])) as f:
            manifest = json.load(f)
        files = manifest["bundle"]["payload"]["files"]
        assert files, f"no files listed for {p['product_id']}"
        for entry in files:
            token = {"sr": "_sr_", "valid": "_valid_", "qapixel": "_qapixel_",
                     "vvvh": "_vvvh_", "dualpol_valid_v2": "_dualpol_valid"}[
                entry.get("role", "")]
            path = find_landed_file(PRODUCTS_DIR, p["product_id"], token)
            assert path is not None, f"landed file missing: {p['product_id']} {entry['role']}"
            if entry.get("size_bytes") is not None:
                assert os.path.getsize(path) == entry["size_bytes"]
            if entry.get("sha256"):
                assert sha256_file(path) == entry["sha256"], path
                checked += 1
    assert checked >= 5


def test_raster_readable_and_finite_sr(index):
    """sr rasters of the first optical products open and contain finite data."""
    optical = [p for p in index["products"]
               if p.get("sensor") in ("landsat8", "landsat7", "sentinel2")]
    assert optical, "no optical products in index"
    for p in optical[:3]:
        path = find_landed_file(PRODUCTS_DIR, p["product_id"], "_sr_")
        assert path is not None, p["product_id"]
        with rasterio.open(path) as src:
            assert src.width > 0 and src.height > 0
            assert src.crs is not None
            win = src.read(1, window=rasterio.windows.Window(0, 0,
                          min(64, src.width), min(64, src.height)))
            arr = np.asarray(win, dtype=np.float64)
            finite = np.isfinite(arr[np.isfinite(arr)]).size
            assert finite > 0


def test_grid_consistency_within_product(index):
    """sr/valid/qapixel roles of one product share the same grid."""
    p = index["products"][0]
    grids = {}
    for token, role in (("_sr_", "sr"), ("_valid_", "valid"), ("_qapixel_", "qapixel")):
        path = find_landed_file(PRODUCTS_DIR, p["product_id"], token)
        if path is None:
            continue
        with rasterio.open(path) as src:
            grids[role] = (src.width, src.height, str(src.crs))
    assert "sr" in grids
    ref = grids["sr"]
    for role, g in grids.items():
        assert g == ref, f"{role} grid {g} != sr grid {ref}"


def test_validator_script_on_sample():
    """The dataset validator exits 0 on a 3-product sample of real bytes."""
    import subprocess
    script = os.path.join(ENGINEERING, "dataset_validation", "validate_landed_products.py")
    r = subprocess.run([sys.executable, script, "--limit", "3"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "failed=0" in r.stdout
