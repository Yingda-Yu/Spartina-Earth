"""Verify the frozen spartina-earth conda environment.

Checks Python, core geospatial/ML packages, GDAL version via rasterio,
and runs a one-minute-scale CUDA smoke test (small random-tensor matmul
on a single visible device; honor CUDA_VISIBLE_DEVICES). Writes a machine
probe JSON to artifacts/system/environment_probe.json.

This script NEVER occupies GPUs: tensors are tiny and freed immediately.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PACKAGES = [
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "sklearn",
    "rasterio",
    "rioxarray",
    "xarray",
    "geopandas",
    "shapely",
    "pyproj",
    "fiona",
    "PIL",
    "matplotlib",
    "pydantic",
    "yaml",
    "pytest",
    "torch",
    "torchvision",
]

VERSION_ATTRS = ("__version__", "VERSION")


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            versions[name] = f"IMPORT_FAILED: {type(exc).__name__}: {exc}"
            continue
        version = None
        for attr in VERSION_ATTRS:
            if hasattr(module, attr):
                version = str(getattr(module, attr))
                break
        if name == "rasterio":
            with contextlib.suppress(Exception):
                from osgeo import gdal  # noqa: F401
            try:
                import rasterio

                version = f"{version} (GDAL {rasterio.__gdal_version__})"
            except Exception:  # noqa: BLE001
                pass
        versions[name] = version
    return versions


def gpu_smoke() -> dict[str, Any]:
    try:
        import torch
    except ImportError:
        return {"status": "SKIPPED", "reason": "torch not importable"}
    if not torch.cuda.is_available():
        return {"status": "FAILED", "reason": "torch.cuda.is_available() is False"}
    device_idx = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(device_idx)
    a = torch.randn(1024, 1024, device="cuda", dtype=torch.float64)
    b = torch.eye(1024, device="cuda", dtype=torch.float64)
    c = a @ b
    residual = float((c - a).abs().max().item())
    del a, b, c
    torch.cuda.synchronize(device_idx)
    return {
        "status": "PASSED",
        "device_index_visible_to_process": device_idx,
        "device_name": props.name,
        "total_memory_gb": round(props.total_memory / 1024**3, 2),
        "matmul_identity_max_residual": residual,
        "residual_tolerance": 1e-8,
        "device_count_visible": torch.cuda.device_count(),
        "torch_cuda_version": torch.version.cuda,
        "visible_devices_env": __import__("os").environ.get("CUDA_VISIBLE_DEVICES"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("artifacts/system/environment_probe.json"))
    parser.add_argument("--expected-python-minor", default="3.11")
    parser.add_argument(
        "--require-gpu",
        action="store_true",
        help="exit non-zero if CUDA smoke does not pass",
    )
    args = parser.parse_args(argv)

    py_full = platform.python_version()
    probe: dict[str, Any] = {
        "probe_time_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "sys_prefix": sys.prefix,
        "python_version": py_full,
        "python_minor_ok": py_full.startswith(args.expected_python_minor + "."),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": package_versions(),
        "gpu_smoke": gpu_smoke(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")

    bad_imports = [k for k, v in probe["packages"].items() if v and v.startswith("IMPORT_FAILED")]
    gpu_ok = probe["gpu_smoke"]["status"] == "PASSED"
    residual = probe["gpu_smoke"].get("matmul_identity_max_residual")
    residual_ok = residual is None or residual <= probe["gpu_smoke"]["residual_tolerance"]
    print(json.dumps(probe["gpu_smoke"], indent=2))
    print(f"python {py_full} minor_ok={probe['python_minor_ok']}")
    print(f"import failures: {bad_imports}")
    print(f"probe -> {args.out}")
    ok = not bad_imports and probe["python_minor_ok"] and residual_ok
    if args.require_gpu:
        ok = ok and gpu_ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
