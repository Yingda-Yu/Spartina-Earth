#!/usr/bin/env python3
"""Issue #21, Phase K -- build the GOLD CANDIDATE registry (CANDIDATE_ONLY).

Deterministic, model-free candidate selection from the frozen NEW panel,
with relevant acquisition dates pulled from the frozen Phase D/E/G
plans. Also computes one extra offline feature for BOUNDARY candidates:
whether GEODATA-2020 positive pixel centres fall within 300 m of the
half-open W10 cell edge (same reprojection/window method as the frozen
feature builder, no resampling).

Outputs:
  benchmarks/spartinashift/v0_2/V0_2_GOLD_CANDIDATE_REGISTRY.json
  benchmarks/spartinashift/v0_2/v02_gold_candidates.csv
  work/issue21/derived/v02_gold_edge_features.csv (derived, gitignored)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.windows import from_bounds

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.v02 import acquisition as A  # noqa: E402
from spartina.benchmark.v02 import gold as G  # noqa: E402
from spartina.data.national.geometry import CHINA_ALBERS_CRS  # noqa: E402
from spartina.data.national.grid import GridKind, GridSpec, parse_cell_id  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
PANEL_CSV = V02_DIR / "v02_cell_panel.csv"
PANEL_JSON = V02_DIR / "SPARTINASHIFT_V0_2_CELL_PANEL.json"
FEATURES_CSV = REPO_ROOT / "work/issue21/derived/v02_cell_features.csv"
S2_JSON = V02_DIR / "V0_2_S2_ACQUISITION_PLAN.json"
L_JSON = V02_DIR / "V0_2_LANDSAT_ACQUISITION_PLAN.json"
G_JSON = V02_DIR / "V0_2_S1_PAIRING_LEDGER.json"
EDGE_CSV = REPO_ROOT / "work/issue21/derived/v02_gold_edge_features.csv"
STAGING = REPO_ROOT / "work/intake/staging"
OUT_JSON = V02_DIR / "V0_2_GOLD_CANDIDATE_REGISTRY.json"
OUT_CSV = V02_DIR / "v02_gold_candidates.csv"

GRID = GridSpec(GridKind.CHINA_ALBERS)


def _one_tif(pattern: str) -> Path:
    matches = sorted(STAGING.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"expected exactly one raster for {pattern}, found "
            f"{[str(m) for m in matches]}")
    return matches[0]


GEODATA_2020_TIF = _one_tif(
    "2020年中国滨海30*m*动态数据集-数据实体/*.tif")


def positive_edge_flag(tif_path: Path,
                       bounds: tuple[float, float, float, float]) -> bool:
    """True if an in-cell positive 30 m centre lies within 300 m of edge."""
    xmin, ymin, xmax, ymax = bounds
    edge = G.EDGE_PROXIMITY_M
    with rasterio.open(tif_path) as ds:
        to_raster = Transformer.from_crs(
            CHINA_ALBERS_CRS, ds.crs, always_xy=True)
        pts = [(xmin, ymin), (xmax, ymax),
               (xmin - edge, ymin - edge), (xmax + edge, ymax + edge)]
        wxs, wys = zip(
            *(to_raster.transform(x, y) for x, y in pts), strict=True)
        window = from_bounds(
            min(wxs), min(wys), max(wxs), max(wys), ds.transform
        ).round_lengths().round_offsets().crop(ds.height, ds.width)
        if window.width <= 0 or window.height <= 0:
            return False
        block = ds.read(1, window=window)
        rows, cols = np.where(block == 1)
        if rows.size == 0:
            return False
        xs, ys = rasterio.transform.xy(
            ds.transform, rows + window.row_off, cols + window.col_off,
            offset="center")
        to_albers = Transformer.from_crs(
            ds.crs, CHINA_ALBERS_CRS, always_xy=True)
        ax, ay = to_albers.transform(np.array(xs), np.array(ys))
        ax = np.asarray(ax)
        ay = np.asarray(ay)
        inside = ((ax >= xmin) & (ax < xmax) & (ay >= ymin) & (ay < ymax))
        if not inside.any():
            return False
        near_edge = (
            (ax[inside] - xmin < edge) | (xmax - ax[inside] < edge)
            | (ay[inside] - ymin < edge) | (ymax - ay[inside] < edge))
        return bool(near_edge.any())


def plan_dates(
    s2_doc: dict[str, Any], l_doc: dict[str, Any],
    g_doc: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for s in s2_doc["slots"]:
        if s["status"] != A.STATUS_ELIGIBLE:
            continue
        d = out.setdefault(s["cell_id"], {
            "s2_eligible_2020": [], "s2_eligible_2021": [],
            "landsat_eligible_2015": [], "landsat_eligible_2020": [],
            "s1_primary_pairs": []})
        d[f"s2_eligible_{s['year']}"].append(
            {"date": str(s["event_utc"])[:10], "tertile": s["tertile"],
             "event_id": s["event_id"]})
    for s in l_doc["slots"]:
        if s["status"] != A.STATUS_ELIGIBLE:
            continue
        d = out.setdefault(s["cell_id"], {
            "s2_eligible_2020": [], "s2_eligible_2021": [],
            "landsat_eligible_2015": [], "landsat_eligible_2020": [],
            "s1_primary_pairs": []})
        d[f"landsat_eligible_{s['year']}"].append(
            {"date": str(s["event_utc"])[:10], "tertile": s["tertile"],
             "sensor": s["sensor"], "event_id": s["event_id"]})
    for p in g_doc["pairings"]:
        if p["status"] != A.STATUS_PAIRED:
            continue
        d = out.setdefault(p["cell_id"], {
            "s2_eligible_2020": [], "s2_eligible_2021": [],
            "landsat_eligible_2015": [], "landsat_eligible_2020": [],
            "s1_primary_pairs": []})
        d["s1_primary_pairs"].append({
            "s2_date": str(p["s2_event_utc"])[:10],
            "s1_date": str(p["s1_event_utc"])[:10],
            "gap_days": p["gap_days"], "pass": p["pass"],
            "relative_orbit": p["relative_orbit"]})
    return out


def main() -> int:
    for path in (S2_JSON, L_JSON, G_JSON):
        if not path.exists():
            raise SystemExit(
                f"missing {path.name}; freeze Phases D/E/G before Phase K")
    panel_freeze = json.loads(PANEL_JSON.read_text("utf-8"))
    s2_doc = json.loads(S2_JSON.read_text("utf-8"))
    l_doc = json.loads(L_JSON.read_text("utf-8"))
    g_doc = json.loads(G_JSON.read_text("utf-8"))
    for name, doc in (("S2 plan", s2_doc), ("Landsat plan", l_doc),
                      ("pairing ledger", g_doc)):
        if A.document_checksum(doc) != doc.get("document_checksum"):
            raise SystemExit(f"frozen {name} checksum mismatch; abort")
    panel_csv_sha = hashlib.sha256(PANEL_CSV.read_bytes()).hexdigest()
    if panel_csv_sha != panel_freeze.get("panel_csv_sha256"):
        raise SystemExit("frozen panel CSV checksum mismatch; abort")

    frame = pd.read_csv(PANEL_CSV)
    feats = pd.read_csv(FEATURES_CSV)[[
        "cell_id", "geodata_2020_pos_px", "cmsa_2020_area_m2",
        "cmsa_2021_area_m2", "center_lon", "center_lat"]]
    feats = feats.rename(columns={
        "geodata_2020_pos_px": "geodata_2020_pos_px_support",
        "cmsa_2020_area_m2": "cmsa_2020_area_m2_support",
        "cmsa_2021_area_m2": "cmsa_2021_area_m2_support"})
    frame = frame.merge(feats, on="cell_id", how="left")

    # Edge feature (cached derived artifact; recompute deterministically).
    edge_flags: dict[str, bool] = {}
    positive = frame[frame["geo20"] == True]["cell_id"].tolist()  # noqa: E712
    for cid in positive:
        ref = parse_cell_id(cid)
        bounds = GRID.cell_bounds_projected(ref.row, ref.col)
        edge_flags[cid] = positive_edge_flag(GEODATA_2020_TIF, bounds)
    pd.DataFrame(
        [{"cell_id": cid, "positive_edge_geodata2020": flag}
         for cid, flag in edge_flags.items()]).to_csv(EDGE_CSV, index=False)
    # edge_flags covers geo20-positive cells only; absence means False.
    frame["positive_edge_geodata2020"] = frame["cell_id"].map(
        edge_flags).isin([True])

    lookup = plan_dates(s2_doc, l_doc, g_doc)
    registry = G.build_registry(frame, lookup)
    registry["panel_selection_checksum"] = panel_freeze[
        "selection_checksum"]
    registry["plan_checksums"] = {
        "s2": s2_doc["document_checksum"],
        "landsat": l_doc["document_checksum"],
        "pairing": g_doc["document_checksum"]}
    registry["generated_utc"] = datetime.now(UTC).isoformat()
    registry["git_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True).stdout.strip()
    registry["document_checksum"] = A.document_checksum(registry)

    csv_rows = pd.DataFrame([
        {"cell_id": c["cell_id"], "province": c["province"],
         "coastal_segment": c["coastal_segment"],
         "center_lon": c["center_lon"], "center_lat": c["center_lat"],
         "candidate_types": "|".join(c["candidate_types"]),
         "agreement_2020": c["source_evidence"]["agreement_2020"],
         "area_class": c["source_evidence"]["area_class"],
         "gold_status": c["gold_status"],
         "high_resolution_evidence_status":
             c["high_resolution_evidence_status"],
         "permission_provenance_status":
             c["permission_provenance_status"]}
        for c in registry["candidates"]])
    csv_rows.to_csv(OUT_CSV, index=False)
    registry["candidate_csv_sha256"] = hashlib.sha256(
        OUT_CSV.read_bytes()).hexdigest()
    registry["document_checksum"] = A.document_checksum(registry)

    if OUT_JSON.exists():
        old = json.loads(OUT_JSON.read_text("utf-8"))
        if old.get("document_checksum") != registry["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN GOLD REGISTRY: existing "
                "document differs")
        print("GOLD registry already frozen and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False,
                       default=str) + "\n")
        print(f"wrote {OUT_JSON}")
    print(f"candidate sites: {registry['n_candidates']}")
    for q in registry["candidate_type_quota"]:
        print(f"  {q['candidate_type']}: {q['selected']}/{q['quota']} "
              f"(pool {q['pool_size']}, regions "
              f"{len(q['regions_used'])})")
        for d in q["deficits_max_attainable"]:
            print(f"  DEFICIT: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
