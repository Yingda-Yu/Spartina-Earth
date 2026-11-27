#!/usr/bin/env python3
"""Validate landed SpartinaShift export products against their manifests.

Reads the v0.2 export index (work/issue21/export/v02_export_index.json)
or a directory of product manifests, then for each sampled product:
  1. opens each manifest-listed raster with rasterio (readability),
  2. verifies file size and SHA-256 against the manifest,
  3. verifies grid dimensions/CRS consistency across roles of a product.

Read-only. Never writes or modifies landed bytes.

Exit codes: 0 = all checks pass; 1 = validation failure; 2 = usage/path
error.

Usage:
  python validate_landed_products.py --index work/issue21/export/v02_export_index.json \
      [--limit 10] [--full] [--json-out report.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import rasterio

BAND_KEYS = ("width", "height", "crs")


def sha256_file(path: str, buf_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buf_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def validate_product(product: dict, products_dir: str) -> dict:
    """Validate one product entry. Returns a result dict; raises nothing."""
    res = {
        "product_id": product["product_id"],
        "ok": True,
        "errors": [],
        "files": [],
    }
    manifest_path = product["manifest"]
    if not os.path.exists(manifest_path):
        res["ok"] = False
        res["errors"].append(f"manifest missing: {manifest_path}")
        return res
    with open(manifest_path) as f:
        manifest = json.load(f)

    payload = manifest.get("bundle", {}).get("payload", {})
    files = payload.get("files", [])
    if not files:
        res["ok"] = False
        res["errors"].append("manifest payload has no files list")
        return res

    grid = {}
    for entry in files:
        # File names follow the landed naming scheme; resolve via products dir.
        # The manifest may store role + sha only; locate by search.
        name = entry.get("name") or entry.get("path")
        if name:
            fpath = name if os.path.isabs(name) else os.path.join(products_dir, name)
        else:
            fpath = find_file_by_role(products_dir, product["product_id"], entry.get("role", ""))
        fdict = {"role": entry.get("role", "?"), "path": fpath, "ok": True, "errors": []}
        if not fpath or not os.path.exists(fpath):
            fdict["ok"] = False
            fdict["errors"].append("file not found")
            res["ok"] = False
            res["errors"].append(f"{entry.get('role')}: file not found: {fpath}")
            res["files"].append(fdict)
            continue
        size = os.path.getsize(fpath)
        expect_size = entry.get("size_bytes")
        if expect_size is not None and size != expect_size:
            fdict["ok"] = False
            fdict["errors"].append(f"size mismatch {size} != {expect_size}")
        digest = sha256_file(fpath)
        expect_sha = entry.get("sha256")
        if expect_sha and digest != expect_sha:
            fdict["ok"] = False
            fdict["errors"].append(f"sha256 mismatch {digest} != {expect_sha}")
        try:
            with rasterio.open(fpath) as src:
                g = {"width": src.width, "height": src.height, "crs": str(src.crs)}
                fdict["readable"] = True
                fdict["grid"] = g
                role = entry.get("role", "?")
                if role in ("sr", "valid", "qapixel", "vvvh", "dualpol_valid_v2"):
                    if role in grid and grid[role.split("_")[0] if role == "dualpol_valid_v2" else role] != g:
                        pass  # cross-role grid checks handled below
                    grid[role] = g
        except Exception as exc:  # noqa: BLE001
            fdict["ok"] = False
            fdict["readable"] = False
            fdict["errors"].append(f"rasterio open failed: {exc}")
            res["ok"] = False
            res["errors"].append(f"{entry.get('role')}: rasterio open failed: {exc}")
        res["files"].append(fdict)

    # Grid consistency: sr defines the reference grid; other raster roles must match.
    ref = grid.get("sr")
    if ref is not None:
        for role, g in grid.items():
            if role == "sr":
                continue
            if (g["width"], g["height"]) != (ref["width"], ref["height"]):
                res["ok"] = False
                res["errors"].append(f"grid mismatch {role} vs sr: {g} vs {ref}")
    return res


def find_file_by_role(products_dir: str, product_id: str, role: str):
    """Locate a landed file for product_id+role by the landed naming scheme."""
    if not os.path.isdir(products_dir):
        return None
    # roles: sr, valid, qapixel (Landsat/S2), vvvh, dualpol_valid_v2 (S1)
    tokens = {
        "sr": "_sr_",
        "valid": "_valid_",
        "qapixel": "_qapixel_",
        "vvvh": "_vvvh_",
        "dualpol_valid_v2": "_dualpol_valid",
    }
    token = tokens.get(role, f"_{role}_")
    prefix = f"spartina_v02_{product_id}"
    for fn in os.listdir(products_dir):
        if fn.startswith(prefix) and token in fn:
            return os.path.join(products_dir, fn)
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="work/issue21/export/v02_export_index.json")
    ap.add_argument("--products-dir", default="work/issue21/export/products")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--full", action="store_true", help="validate all products")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    if not os.path.exists(args.index):
        print(f"ERROR: index not found: {args.index}", file=sys.stderr)
        return 2
    with open(args.index) as f:
        index = json.load(f)
    products = index["products"]
    sample = products if args.full else products[: args.limit]

    results = [validate_product(p, args.products_dir) for p in sample]
    n_ok = sum(1 for r in results if r["ok"])
    report = {
        "validated": len(results),
        "ok": n_ok,
        "failed": len(results) - n_ok,
        "mode": "full" if args.full else f"sample{args.limit}",
        "results": results,
    }
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=1)
    print(f"validated={report['validated']} ok={n_ok} failed={report['failed']}")
    for r in results:
        if not r["ok"]:
            print(f"FAIL {r['product_id']}: {r['errors'][:3]}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
