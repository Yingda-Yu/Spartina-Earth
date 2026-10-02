#!/usr/bin/env python3
"""Region-wide S2 datatake supplement (M2.1a2, Issue #12).

The M2.1a census did not record DATATAKE_IDENTIFIER or S2 relative orbit.
Multi-tile acquisition grouping needs the real datatake key, so this
script makes exactly ONE metadata getInfo per Sentinel-2 year (2017-2026,
10 calls) over a single polygon spanning all three bays. No pixels, no
Export (guard live). The original census table is never modified; output
is the supplemental manifest keyed by scene_id.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from spartina.data.zhejiang.census import install_export_guard  # noqa: E402

COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
# Single polygon covering all three bay envelopes with margin.
REGION_WESN = (120.83, 27.93, 122.02, 30.94)
YEARS = range(2017, 2027)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",
                        default=str(REPO_ROOT
                                    / "configs/data/zhejiang_multibay_m21a.yaml"))
    parser.add_argument("--manifest-dir",
                        default=str(REPO_ROOT / "datasets/manifests"))
    args = parser.parse_args()

    out_path = (Path(args.manifest_dir)
                / "zhejiang_s2_datatake_supplement_v0.parquet")

    import ee

    from spartina.data.gee import auth
    if not auth.credentials_available():
        print("ERROR: GEE credentials unavailable", file=sys.stderr)
        return 2
    auth.initialize()
    restore = install_export_guard(ee)
    retrieval_ts = datetime.now(UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    minx, miny, maxx, maxy = REGION_WESN
    region = ee.Geometry.Rectangle([minx, miny, maxx, maxy],
                                   "EPSG:4326", False)
    rows: list[dict[str, Any]] = []
    try:
        for year in YEARS:
            coll = (
                ee.ImageCollection(COLLECTION)
                .filterBounds(region)
                .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
            )

            def annotate(image: Any) -> Any:
                return ee.Feature(None, {
                    "id": image.id(),
                    "dt": image.get("DATATAKE_IDENTIFIER"),
                    "tile": image.get("MGRS_TILE"),
                    "sc": image.get("SPACECRAFT_NAME"),
                    "rel": image.get("relativeOrbitNumber_start"),
                    "t": image.date().format(
                        "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"),
                })

            payload: dict[str, Any] = coll.map(annotate).getInfo()
            feats = payload.get("features", [])
            for f in feats:
                p = f.get("properties", {}) or {}
                rows.append({
                    "scene_id": p.get("id"),
                    "datatake_identifier": p.get("dt") or "",
                    "mgrs_tile": p.get("tile"),
                    "spacecraft": p.get("sc"),
                    "relative_orbit_number": p.get("rel"),
                    "sensing_utc": p.get("t"),
                    "retrieval_timestamp": retrieval_ts,
                })
            n_dt = sum(1 for r in rows
                       if r["datatake_identifier"]
                       and r["sensing_utc"][:4] == str(year))
            print(f"{year}: {len(feats)} scenes, {n_dt} with datatake")
            time.sleep(0.35)
    finally:
        restore()

    df = pd.DataFrame(rows).drop_duplicates("scene_id")
    missing = int((df["datatake_identifier"] == "").sum())
    print(f"total {len(df)} unique scenes; datatake missing for {missing}")
    df.to_parquet(out_path, index=False)
    print(f"wrote {out_path.relative_to(REPO_ROOT)} "
          f"({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
