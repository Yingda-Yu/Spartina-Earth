#!/usr/bin/env python3
"""Rescue fetch for the hung S2 affected-range years (R1 Parts C/E).

The main ``fetch_r1_affected_ranges.py`` process stalled inside a single
yearly ``aggregate_arrays.getInfo`` with no socket deadline. This rescue
reuses the identical server filter (bbox 132 rectangle AND
``bounds(NE union) OR inList(added MGRS tiles)``) but:

* skips years already present as raw per-year cache;
* fetches missing years as two half-year scopes with a hard per-call
  wall-clock deadline (``signal.alarm``), retrying once;
* concatenates cached yearly + half-year payloads (de-duplicated on
  ``system:index``) and applies the same keep rules as the main
  fetcher, producing the same S2 incremental parquet;
* rebuilds the complete incremental resource ledger from ALL raw
  caches (landsat + S2), marking reconstructed-from-cache calls.

Metadata-only; export guard installed; zero pixel exports.
"""

from __future__ import annotations

import argparse
import csv
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import mapping

from spartina.data.gee.auth import initialize
from spartina.data.national.census_join import load_cells
from spartina.data.national.census_ledger import ResourceLedger
from spartina.data.national.scene_events import s2_granule_from_props
from spartina.data.zhejiang.census import install_export_guard

# Bbox/collection must match fetch_r1_affected_ranges.DOMAIN_BBOX exactly.
DOMAIN_BBOX = (105.0, 15.0, 132.0, 43.0)
S2_PROPS = (
    "system:index",
    "PRODUCT_ID",
    "DATATAKE_IDENTIFIER",
    "MGRS_TILE",
    "SPACECRAFT_NAME",
    "system:time_start",
    "CLOUDY_PIXEL_PERCENTAGE",
    "CLOUDY_PIXEL_OVER_LAND_PERCENTAGE",
)

MISSING_YEARS = (2022, 2023, 2024, 2025)
HALVES = (("H1", "-01-01", "-07-01"), ("H2", "-07-01", "-01-01"))
CALL_DEADLINE_S = 900


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class _DeadlineError(Exception):
    pass


def _alarm_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
    raise _DeadlineError(f"getInfo exceeded {CALL_DEADLINE_S}s")


def _fetch_scope(
    collection_builder: Any,
    scope: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    import ee  # local import after initialize

    collection = collection_builder(start, end)
    last_exc: Exception | None = None
    for attempt in (1, 2):
        started = time.perf_counter()
        try:
            signal.signal(signal.SIGALRM, _alarm_handler)
            signal.alarm(CALL_DEADLINE_S)
            try:
                columns = [
                    collection.aggregate_array(q) for q in S2_PROPS
                ]
                raw_payload = ee.Dictionary.fromLists(
                    list(S2_PROPS), columns
                ).getInfo()
            finally:
                signal.alarm(0)
            if not isinstance(raw_payload, dict):
                raise RuntimeError(f"unexpected payload type for {scope}")
            payload: dict[str, Any] = dict(raw_payload)
            payload["_meta"] = {
                "scope": scope,
                "retries": attempt - 1,
                "duration_s": round(time.perf_counter() - started, 3),
                "reconstructed": False,
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"scope {scope} failed after retries: {last_exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--r1-dir", type=Path, default=Path("work/national/census_r1")
    )
    parser.add_argument(
        "--v0-dir", type=Path, default=Path("work/national/census")
    )
    parser.add_argument(
        "--cells-csv",
        type=Path,
        default=Path("work/national/domain/cells_china_albers_W10000.csv"),
    )
    parser.add_argument(
        "--ne-cells-csv",
        type=Path,
        default=Path("datasets/manifests/china_ne_chronic_zero_audit_v0.csv"),
    )
    parser.add_argument(
        "--mgrs-v01-index",
        type=Path,
        default=Path("work/national/footprints/mgrs_china_coast_v0_1_index.csv"),
    )
    args = parser.parse_args()

    out_dir = args.r1_dir / "incremental"
    raw_dir = out_dir / "raw"

    with args.mgrs_v01_index.open(newline="", encoding="utf-8") as handle:
        mgrs_v01 = {r["mgrs_tile"] for r in csv.DictReader(handle)}
    v0 = pd.read_parquet(args.v0_dir / "scene_census_sentinel2_v0.parquet")
    v0_ids = set(v0["system_index"].astype(str))

    ne_ids = set(pd.read_csv(args.ne_cells_csv)["cell_id"].astype(str))
    cells = load_cells(args.cells_csv)
    ne_union = cells[cells["cell_id"].isin(ne_ids)].geometry.union_all()

    initialize()
    import ee

    install_export_guard(ee)
    roi_bbox = ee.Geometry.Rectangle(list(DOMAIN_BBOX), "EPSG:4326", False)
    ne_geom = ee.Geometry(mapping(ne_union))

    added_tiles = sorted(
        set(
            pd.read_csv(
                Path("work/national/footprints/mgrs_china_coast_v0_1_index.csv")
            )["mgrs_tile"].astype(str)
        )
        - set(
            pd.read_csv(
                Path("work/national/footprints/mgrs_china_coast_index.csv")
            )["mgrs_tile"].astype(str)
        )
    )

    def builder(start: str, end: str) -> Any:
        return (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(roi_bbox)
            .filterDate(start, end)
            .filter(
                ee.Filter.Or(
                    ee.Filter.bounds(ne_geom),
                    ee.Filter.inList("MGRS_TILE", added_tiles),
                )
            )
        )

    ledger = ResourceLedger(
        run_id="affected-ranges-r1-s2-rescue", git_commit=_git_commit()
    )
    ledger.note("Rescue: half-year scopes with 900s per-call deadline")

    def _run_and_cache(
        scope: str, start: str, end: str, cache: Path
    ) -> int:
        if cache.exists():
            return -1
        print(f"fetch {scope} {start}..{end}", flush=True)
        payload = _fetch_scope(builder, scope, start, end)
        n = len(payload.get(S2_PROPS[0], []))
        ledger.record_call(
            sensor="sentinel2",
            call_kind="aggregate_arrays.getInfo",
            scope=scope,
            n_results=n,
            payload_bytes=len(json.dumps(payload, default=str).encode()),
            duration_s=float(payload["_meta"]["duration_s"]),
            retries=int(payload["_meta"]["retries"]),
        )
        cache.write_text(
            json.dumps(payload, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"{scope}: returned={n}", flush=True)
        return n

    # --- live fetch of missing years (half-year; quarter fallback) -------
    quarters = (("Q3", "-07-01", "-10-01"), ("Q4", "-10-01", "-01-01"))
    def _quarters_for(year: int) -> None:
        for quarter, qa, qb in quarters:
            _run_and_cache(
                f"sentinel2:{year}{quarter}",
                f"{year}{qa}",
                f"{year + (1 if quarter == 'Q4' else 0)}{qb}",
                raw_dir / f"sentinel2_{year}{quarter}.json",
            )

    for year in MISSING_YEARS:
        for half, a, b in HALVES:
            cache = raw_dir / f"sentinel2_{year}{half}.json"
            fail_marker = raw_dir / f".halffailed_{year}{half}"
            if fail_marker.exists():
                _quarters_for(year)
                continue
            start = f"{year}{a}"
            end = f"{year + (1 if half == 'H2' else 0)}{b}"
            try:
                _run_and_cache(
                    f"sentinel2:{year}{half}", start, end, cache
                )
            except RuntimeError as exc:
                # Server-side computation timeout: split the half year
                # into two quarters and remember not to retry the half.
                print(f"rescue quarter split: {exc}", flush=True)
                fail_marker.write_text(str(exc)[:500], encoding="utf-8")
                _quarters_for(year)

    # --- build S2 incremental parquet from ALL S2 caches -----------------
    new_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    s2_caches = sorted(raw_dir.glob("sentinel2_*.json"))
    for cache in s2_caches:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        columns = {p: list(payload.get(p, [])) for p in S2_PROPS}
        n = len(columns[S2_PROPS[0]])
        for i in range(n):
            props = {
                p: columns[p][i] if i < len(columns[p]) else None
                for p in S2_PROPS
            }
            granule = s2_granule_from_props(props)
            if granule is None or granule.mgrs_tile not in mgrs_v01:
                continue
            if granule.system_index in v0_ids or granule.system_index in seen:
                continue
            row = granule.to_row()
            row["year_status"] = "FULL_YEAR"
            row["census_cutoff_utc"] = None
            new_rows.append(row)
            seen.add(granule.system_index)

    frame = pd.DataFrame(new_rows)
    out_path = out_dir / "scene_census_sentinel2_incremental_v0_1.parquet"
    frame.to_parquet(out_path, index=False)
    print(f"sentinel2 incremental rows: {len(frame)} -> {out_path}", flush=True)

    # --- rebuild the FULL incremental ledger from raw caches -------------
    full_ledger = ResourceLedger(
        run_id="affected-ranges-r1", git_commit=_git_commit()
    )
    full_ledger.note(
        "R1 PARTS C/E: incremental metadata for v0-affected ranges "
        "(ledger rebuilt by rescue script; per-year landsat/s2 cache "
        "calls reconstructed from raw JSON)"
    )
    for cache in sorted(raw_dir.glob("*.json")):
        payload = json.loads(cache.read_text(encoding="utf-8"))
        name = cache.stem  # e.g. landsat5_1984 / sentinel2_2022H1
        sensor, token = name.split("_", 1)
        meta = payload.get("_meta") if isinstance(payload, dict) else None
        # First id column length is authoritative for the result count.
        if sensor == "sentinel2":
            n_results = len(payload.get("system:index", []))
        else:
            n_results = len(payload.get("LANDSAT_SCENE_ID", []))
        full_ledger.record_call(
            sensor=sensor,
            call_kind="aggregate_arrays.getInfo",
            scope=f"{sensor}:{token}",
            n_results=n_results,
            payload_bytes=cache.stat().st_size,
            duration_s=float(meta["duration_s"]) if meta else 0.0,
            retries=int(meta["retries"]) if meta else 0,
        )
    for parquet in sorted(out_dir.glob("scene_census_*_incremental_v0_1.parquet")):
        full_ledger.record_cache_file(parquet)
        full_ledger.note(f"{parquet.name}: new_scenes rows present")
    ledger_path = out_dir / "resource_ledger_incremental_r1.json"
    full_ledger.write(ledger_path)
    print(f"ledger -> {ledger_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
