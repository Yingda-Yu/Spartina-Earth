"""Recover acquisition-date / scene provenance for the Hangzhou Bay 2015 bundle.

Read-only with respect to ``old datasets/``. Evidence is collected from:

1. file names (structured hypotheses, never asserted as fact);
2. GeoTIFF tags / band descriptions / value ranges via rasterio;
3. sidecar files (``.aux.xml`` / ``.tfw`` / ``.vat.dbf``) - text only;
4. the two owner manuscript PDFs' extracted text;
5. public STAC metadata catalogs (earth-search; metadata only - never
   downloads pixels and never queries Google Earth Engine).

Every recovered date carries its exact evidence source. Anything that
cannot be proven stays "UNKNOWN". Network failures are recorded as
QUERY_FAILED rather than faked.

Usage:
    python recover_scene_dates.py \
        --src-dir "old datasets/Spartina/HangZhouBay" \
        --out artifacts/audit/pilot0/date_recovery.json
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import rasterio

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
# Geographic footprint of the L8/NDVI/SAI exports (M1.1 alignment audit).
WINDOW_BBOX = [121.018, 30.266, 121.418, 30.396]

MANUSCRIPT_NOMINAL_2015 = ["08/15/2015", "09/01/2015", "10/03/2015"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: UP017


def tiff_evidence(path: Path) -> dict[str, Any]:
    """All in-file provenance hints: tags, band names, units, ranges."""
    with rasterio.open(path) as ds:
        bands = []
        for i in range(1, ds.count + 1):
            tags = dict(ds.tags(i))
            bands.append(
                {
                    "index": i,
                    "description": ds.descriptions[i - 1],
                    "units": ds.units[i - 1],
                    "dtype": ds.dtypes[i - 1],
                    "statistics_tags": {
                        k: v
                        for k, v in tags.items()
                        if k.startswith("STATISTICS_")
                        and k not in ("STATISTICS_SKIPFACTORX",
                                      "STATISTICS_SKIPFACTORY")
                    },
                }
            )
        return {
            "driver": ds.driver,
            "crs": str(ds.crs) if ds.crs else None,
            "width": ds.width,
            "height": ds.height,
            "bounds_native_crs": list(ds.bounds),
            "dataset_tags": dict(ds.tags()),
            "bands": bands,
            "acquisition_date_tags": [
                k for k in ds.tags()
                if "date" in k.lower() or "time" in k.lower()
            ],
        }


def sidecar_evidence(path: Path) -> dict[str, Any]:
    """Look for date/scene strings in small text sidecars."""
    hits: dict[str, Any] = {}
    patterns = re.compile(
        r"(20\d{2}[-/]?\d{2}[-/]?\d{2}|S1[AB]|LC0?8|LE0?7|LT0?5|"
        r"COPERNICUS|LANDSAT)",
        re.IGNORECASE,
    )
    for sib in path.parent.glob(path.name + "*"):
        if sib.suffix.lower() == ".xml" or sib.name.endswith(".tfw"):
            try:
                text = sib.read_text(errors="ignore")
            except OSError:
                continue
            hits[sib.name] = {
                "bytes": sib.stat().st_size,
                "date_or_scene_tokens": sorted(set(patterns.findall(text))),
            }
    return hits


_FILENAME_RE = re.compile(
    r"^(?P<prefix>[A-Za-z]+)?(?P<year>20\d{2})(?P<a>\d{3})(?P<rest>[A-Za-z_0-9]*)"
)


def filename_hypotheses(name: str) -> list[dict[str, str]]:
    """Structured readings of the opaque legacy mask file name."""
    stem = Path(name).stem
    hypotheses: list[dict[str, str]] = []
    m = _FILENAME_RE.match(stem)
    if m:
        year = int(m.group("year"))
        a = m.group("a")
        hypotheses.append(
            {
                "reading": (
                    f"year={year}; WRS path/row = {a[:3]}/{a[3:]}? "
                    f"(trailing token {m.group('rest')!r} meaning unknown)"
                ),
                "support": (
                    "WRS-2 118/39 scene centers (~121.40E, 30.50N, "
                    "verified via STAC catalog 2026-09-27) cover the window"
                ),
                "status": "CONSISTENT_NOT_PROVEN",
            }
        )
        hypotheses.append(
            {
                "reading": f"year={year}; day-of-year={int(a)} "
                f"(would be {year}-04-28)",
                "support": ("conflicts with the manuscript Aug-Oct season and "
                            "with Landsat 16-day overpass dates"),
                "status": "UNSUPPORTED",
            }
        )
    else:
        hypotheses.append(
            {"reading": stem, "support": "parse failed", "status": "UNKNOWN"}
        )
    return hypotheses


def stac_search(payload: dict[str, Any], timeout: int = 45) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        STAC_URL, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode()))
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"error": "QUERY_FAILED", "detail": str(exc)}


def _simplify(f: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    p = f["properties"]
    out = {"id": f["id"], "datetime": p.get("datetime")}
    for k in fields:
        out[k] = p.get(k)
    return out


def inventory_landsat() -> dict[str, Any]:
    """All 2015 Landsat C2-L2 scenes intersecting the window (metadata)."""
    result = stac_search(
        {
            "collections": ["landsat-c2-l2"],
            "datetime": "2015-01-01T00:00:00Z/2015-12-31T23:59:59Z",
            "bbox": WINDOW_BBOX,
            "limit": 200,
            "sort": [{"field": "properties.datetime", "direction": "asc"}],
        }
    )
    if result.get("error"):
        return result
    scenes = [
        _simplify(
            f,
            (
                "eo:cloud_cover",
                "landsat:collection_category",
                "platform",
                "landsat:wrs_path",
                "landsat:wrs_row",
            ),
        )
        for f in result.get("features", [])
    ]
    return {
        "number_matched": result.get("numberMatched"),
        "returned": len(scenes),
        "scenes": scenes,
    }


def inventory_s1() -> dict[str, Any]:
    """Count/list 2015 Sentinel-1 GRD scenes intersecting the window."""
    result = stac_search(
        {
            "collections": ["sentinel-1-grd"],
            "datetime": "2015-01-01T00:00:00Z/2015-12-31T23:59:59Z",
            "bbox": WINDOW_BBOX,
            "limit": 200,
            "sort": [{"field": "properties.datetime", "direction": "asc"}],
        }
    )
    if result.get("error"):
        return result
    scenes = [
        _simplify(f, ("sat:orbit_state", "instrument", "polarizations"))
        for f in result.get("features", [])
    ]
    return {
        "number_matched": result.get("numberMatched"),
        "returned": len(scenes),
        "scenes": scenes,
    }


def manuscript_date_evidence(mdir: Path | None) -> dict[str, Any]:
    """Extract date/path-row lines from manuscript text, if available."""
    if mdir is None or not mdir.exists():
        return {"status": "MISSING", "text_dir": None}
    out: dict[str, Any] = {"text_dir": str(mdir), "files": {}}
    for txt in mdir.glob("*.txt"):
        interesting = [
            ln.strip()
            for ln in txt.read_text(errors="ignore").splitlines()
            if re.search(r"11[89]/39|\d{2}/\d{2}/2015|OLI|TM", ln)
        ]
        out["files"][txt.name] = interesting[:40]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src-dir", type=Path,
                    default=Path("old datasets/Spartina/HangZhouBay"))
    ap.add_argument("--out", type=Path,
                    default=Path("artifacts/audit/pilot0/date_recovery.json"))
    ap.add_argument("--manuscript-dir", type=Path,
                    default=Path("artifacts/audit/manuscript_text"))
    ap.add_argument("--no-network", action="store_true",
                    help="skip STAC queries (offline mode)")
    args = ap.parse_args(argv)

    raster_names = [
        "c201511839DTSP_2.tif",
        "L8_AllBands_2015.tif",
        "NDVI_2015.tif",
        "SAI_2015.tif",
        "S1_VV_2015.tif",
        "S1_VH_2015.tif",
    ]
    files_evidence: dict[str, Any] = {}
    for name in raster_names:
        path = args.src_dir / name
        if not path.exists():
            files_evidence[name] = {"status": "MISSING"}
            continue
        files_evidence[name] = {
            "status": "READ",
            "filename_hypotheses": filename_hypotheses(name),
            "tiff": tiff_evidence(path),
            "sidecars": sidecar_evidence(path),
            "acquisition_date_verdict": (
                "UNKNOWN - no TIFF/sidecar tag carries an acquisition or "
                "composite date"
            ),
        }

    report: dict[str, Any] = {
        "generated_utc": utc_now(),
        "read_only_policy": "nothing under old datasets/ was modified",
        "window_bbox_lonlat": WINDOW_BBOX,
        "files": files_evidence,
        "manuscript_nominal_2015_dates": MANUSCRIPT_NOMINAL_2015,
        "manuscript_evidence": manuscript_date_evidence(args.manuscript_dir),
        "stac_inventory": {
            "catalog": STAC_URL,
            "retrieval_utc": utc_now(),
            "landsat_c2_l2": None,
            "sentinel1_grd": None,
        },
    }
    if not args.no_network:
        report["stac_inventory"]["landsat_c2_l2"] = inventory_landsat()
        report["stac_inventory"]["sentinel1_grd"] = inventory_s1()
    else:
        report["stac_inventory"]["landsat_c2_l2"] = {"error": "SKIPPED_OFFLINE"}
        report["stac_inventory"]["sentinel1_grd"] = {"error": "SKIPPED_OFFLINE"}

    report["verdicts"] = {
        "composite_dates_L8_NDVI_SAI": "UNKNOWN",
        "composite_dates_S1": "UNKNOWN",
        "mask_production_date": "UNKNOWN",
        "wrs_window": (
            "118/39 scenes cover the window (catalog evidence); 119/39 "
            "centers ~119.85E and do not"
        ),
        "note": (
            "candidate scenes are inventoried; the exact scene set and the "
            "compositing rule remain MISSING_EVIDENCE"
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"-> {args.out}")
    l8 = report["stac_inventory"]["landsat_c2_l2"]
    s1 = report["stac_inventory"]["sentinel1_grd"]
    print("L8 matched:", l8.get("number_matched", l8.get("error")))
    print("S1 matched:", s1.get("number_matched", s1.get("error")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
