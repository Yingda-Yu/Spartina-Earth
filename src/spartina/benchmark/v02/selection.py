"""Issue #21, Phase B — deterministic, model-free v0.2 cell selection.

The selector consumes ONLY the frozen national feature table
(frozen geography, target-independent provinces, named label-source
presence/area, Issue #18 strata, patch/area class, metadata-only EO
availability). No model output, error, uncertainty, or imagery can
enter any decision.

Ordering is a fixed sequence of predeclared quota slots built to meet
the Phase A support goals. Within every slot cells are ranked by EO
metadata richness, then by a slot-salted SHA-256 hash rank, then by
cell id. The panel is a union: a cell is picked once and every slot
that selects it is recorded as an inclusion reason.

Nothing here trains or runs a model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

import pandas as pd

from spartina.benchmark.v02.requirements import (
    MAX_NEW_CELLS,
    REQUIREMENTS_NAME,
    selection_hash_rank,
)
from spartina.data.national.pilot_panel import label_agreement_category_2020

#: One 30 m source pixel; presence threshold for named raster labels.
PRESENCE_AREA_M2: Final[float] = 900.0

#: Area classes (km^2 of the largest named-positive source in cell).
AREA_CLASS_ORDER: Final[tuple[str, ...]] = (
    "NONE", "TRACE", "SMALL", "MEDIUM", "LARGE")
AREA_CLASS_UPPER_KM2: Final[dict[str, float]] = {
    "NONE": 0.0, "TRACE": 0.05, "SMALL": 0.5, "MEDIUM": 5.0,
    "LARGE": float("inf")}

GEO_GOAL: Final[int] = 12
GEO_REGIONS_GOAL: Final[int] = 3
CMSA_GOAL: Final[int] = 24
CMSA_REGIONS_GOAL: Final[int] = 4
HOLDOUT_GOAL: Final[int] = 4
HELD_POSITIVE_MIN: Final[int] = 2
HELD_CELLS_MIN: Final[int] = 4
OUTSIDE_CELLS_MIN: Final[int] = 12
OUTSIDE_POSITIVE_MIN: Final[int] = 4
PAIR_GOAL: Final[int] = 24
PAIR_POSITIVE_GOAL: Final[int] = 12
BACKGROUND_GOAL: Final[int] = 24
BACKGROUND_REGIONS_GOAL: Final[int] = 4

REASON_OLD_PANEL: Final[str] = "STAGE1_DEVELOPMENT_INSTRUMENTATION_ONLY"
REASON_DOMAIN: Final[str] = (
    "OUTSIDE_W10_DOMAIN_V1_CORE_FROZEN_OR_NOT_PRODUCTION")
REASON_RANK: Final[str] = "ELIGIBLE_BUT_NOT_REQUIRED_BY_FROZEN_QUOTA_RANK"


def area_class(area_km2: float) -> str:
    if area_km2 <= 0.0:
        return "NONE"
    for name in ("TRACE", "SMALL", "MEDIUM", "LARGE"):
        if area_km2 <= AREA_CLASS_UPPER_KM2[name]:
            return name
    raise ValueError(f"no area class for {area_km2}")


def annotate(features: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic label/EO/stratum flags to the feature table."""
    df = features.copy()
    df["geo15"] = df["geodata_2015_pos_px"] >= 1
    df["geo20"] = df["geodata_2020_pos_px"] >= 1
    df["cmsa20"] = df["cmsa_2020_area_m2"] >= PRESENCE_AREA_M2
    df["cmsa21"] = df["cmsa_2021_area_m2"] >= PRESENCE_AREA_M2
    df["cmssm20"] = df["cmssm_2020_issue18_m_px"] >= 1
    df["geo_both"] = df["geo15"] & df["geo20"]
    df["cmsa_both"] = df["cmsa20"] & df["cmsa21"]
    df["any_positive"] = (
        df["geo15"] | df["geo20"] | df["cmsa20"] | df["cmsa21"]
        | df["cmssm20"])
    df["gridcode0_unknown_overlap"] = (
        (df["cmsa_2020_gridcode0_area_m2"] > 0)
        | (df["cmsa_2021_gridcode0_area_m2"] > 0))
    df["clean_background"] = (
        ~df["any_positive"] & ~df["gridcode0_unknown_overlap"])
    df["pair20"] = (
        (df["s2_autumn_full_2020"] >= 1)
        & (df["s1_autumn_full_2020"] >= 1))
    df["pair21"] = (
        (df["s2_autumn_full_2021"] >= 1)
        & (df["s1_autumn_full_2021"] >= 1))
    df["pair_capable"] = df["pair20"] | df["pair21"]
    df["n_pair_years"] = df["pair20"].astype(int) + df["pair21"].astype(int)
    df["landsat_both_years"] = (
        (df["landsat_autumn_full_2015"] >= 1)
        & (df["landsat_autumn_full_2020"] >= 1))
    df["island"] = df["membership_v1_1"] == "KEEP_ISLAND_COASTAL"
    df["agreement_2020"] = [
        label_agreement_category_2020(g, c, m)
        for g, c, m in zip(
            df["geo20"], df["cmsa20"], df["cmssm20"], strict=True)]
    geo_km2 = df["geodata_2020_pos_px"].astype(float) * 900.0 / 1e6
    cmsa_km2 = df[
        ["cmsa_2020_area_m2", "cmsa_2021_area_m2"]].max(axis=1) / 1e6
    df["max_pos_area_km2"] = pd.concat(
        [geo_km2, cmsa_km2], axis=1).max(axis=1)
    df["area_class"] = [area_class(float(v)) for v in df["max_pos_area_km2"]]
    return df


def panel_checksum(cell_ids: list[str], holdout_provinces: list[str]
                   ) -> str:
    body = {
        "requirements": REQUIREMENTS_NAME,
        "selected": sorted(cell_ids),
        "holdout_provinces": holdout_provinces,
    }
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ranked(frame: pd.DataFrame, slot: str) -> pd.DataFrame:
    ranks = {
        cid: selection_hash_rank(f"slot:{slot}", cid)
        for cid in frame["cell_id"]}
    out = frame.assign(hash_rank=frame["cell_id"].map(ranks))
    return out.sort_values([
        "n_pair_years", "s2_autumn_full_2020", "s2_autumn_full_2021",
        "s1_autumn_full_2020", "s1_autumn_full_2021",
        "landsat_autumn_full_2015", "landsat_autumn_full_2020",
        "hash_rank", "cell_id"],
        ascending=[False, False, False, False, False, False, False,
                   True, True])


def select_panel(features: pd.DataFrame) -> dict[str, Any]:
    """Run the fixed deterministic quota sequence and return the panel."""
    df = annotate(features)
    universe = df[
        ~df["old_stage1_panel"]
        & df["membership_v1_1"].isin(
            ("KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL"))
        & (df["production_eligible"].astype(str).str.lower() == "true")
    ].copy()
    index = universe.set_index("cell_id", drop=False)

    inclusion: dict[str, list[str]] = {}

    def take(slot: str, pool: pd.DataFrame, n: int,
             prefer: pd.Series | None = None) -> list[str]:
        picked: list[str] = []
        frames: list[pd.DataFrame] = []
        if prefer is not None:
            pref = prefer.reindex(pool.index, fill_value=False)
            frames.append(pool[pref])
            frames.append(pool[~pref])
        else:
            frames.append(pool)
        for frame in frames:
            if len(picked) >= n:
                break
            for cell_id in _ranked(frame, slot)["cell_id"]:
                if cell_id in inclusion:
                    continue
                picked.append(cell_id)
                inclusion.setdefault(cell_id, []).append(slot)
                if len(picked) >= n:
                    break
        return picked

    deficits: list[str] = []
    known = universe[universe["province"] != "UNKNOWN"]

    # -- Holdout designation BEFORE any cell is picked ---------------
    pos_candidates = known[
        (known["geo_both"] | known["cmsa_both"]) & known["pair_capable"]]
    bg_candidates = known[known["clean_background"] & known["pair_capable"]]
    stats = pd.DataFrame({
        "n_pos": pos_candidates.groupby("province").size(),
        "n_bg": bg_candidates.groupby("province").size()}).fillna(0)
    stats = stats.astype(int)
    eligible = stats[(stats["n_pos"] >= HELD_POSITIVE_MIN)
                     & (stats["n_bg"] >= 2)]
    holdouts = eligible.sort_values(
        ["n_pos", "n_bg", "province"],
        ascending=[False, False, True]).index.tolist()[:HOLDOUT_GOAL]
    if len(holdouts) < HOLDOUT_GOAL:
        deficits.append(
            f"only {len(holdouts)} provinces meet holdout criteria "
            f"(>= {HELD_POSITIVE_MIN} double-positive pair-capable + "
            f">=2 background pair-capable); goal {HOLDOUT_GOAL}")

    # -- Slot 1: per-holdout 2 positives + 2 background --------------
    for prov in holdouts:
        positives = known[
            (known["province"] == prov)
            & (known["geo_both"] | known["cmsa_both"])]
        take("holdout_positive_geo", positives, 1,
             prefer=positives["geo_both"])
        take("holdout_positive_cmsa", positives, 1,
             prefer=positives["cmsa_both"])
        background = known[(known["province"] == prov)
                           & known["clean_background"]]
        take("holdout_background", background, 2,
             prefer=background["pair_capable"])

    def ids() -> set[str]:
        return set(inclusion)

    # -- Slots 2-3: round-robin province spread of temporal positives
    def spread_fill(slot: str, flag: str, goal_n: int, goal_regions: int
                    ) -> None:
        provinces = sorted(universe.loc[
            universe[flag] & (universe["province"] != "UNKNOWN"),
            "province"].unique())

        def support_counts() -> tuple[int, int]:
            sub = universe[universe["cell_id"].isin(ids()) & universe[flag]]
            return (len(sub),
                    sub[sub["province"] != "UNKNOWN"]["province"].nunique())

        rounds = 0
        while True:
            n_have, regions_have = support_counts()
            if n_have >= goal_n and regions_have >= goal_regions:
                break
            progressed = False
            for prov in provinces:
                pool = universe[(universe["province"] == prov)
                                & universe[flag]]
                if take(slot, pool, 1, prefer=pool["pair_capable"]):
                    progressed = True
                n_have, regions_have = support_counts()
                if n_have >= goal_n and regions_have >= goal_regions:
                    break
            rounds += 1
            if not progressed or rounds > len(provinces) + goal_n:
                break
        n_have, regions_have = support_counts()
        if n_have < goal_n:
            deficits.append(
                f"{slot}: max attainable {n_have} cells < goal {goal_n}")
        if regions_have < goal_regions:
            deficits.append(
                f"{slot}: max attainable {regions_have} regions < goal "
                f"{goal_regions}")

    spread_fill("geodata_both_years", "geo_both",
                GEO_GOAL, GEO_REGIONS_GOAL)
    spread_fill("cmsa_both_years", "cmsa_both",
                CMSA_GOAL, CMSA_REGIONS_GOAL)

    # -- Slot 4: outside-pool guarantee for every holdout ------------
    positive_ids = set(universe.loc[
        universe["geo_both"] | universe["cmsa_both"], "cell_id"])
    for prov in holdouts:
        selected = ids()
        outside = {c for c in selected
                   if index.loc[c, "province"] != prov}
        if len(outside) < OUTSIDE_CELLS_MIN:
            pool = universe[universe["province"] != prov]
            take("outside_cells_guarantee", pool,
                 OUTSIDE_CELLS_MIN - len(outside))
        out_pos = outside & positive_ids
        if len(out_pos) < OUTSIDE_POSITIVE_MIN:
            pool = universe[(universe["province"] != prov)
                            & (universe["geo_both"] | universe["cmsa_both"])]
            take("outside_positive_guarantee", pool,
                 OUTSIDE_POSITIVE_MIN - len(out_pos),
                 prefer=pool["pair_capable"])

    # -- Slot 5: near-synchronous pairing goals ----------------------
    def pair_counts() -> tuple[int, int]:
        sub = universe[universe["cell_id"].isin(ids())]
        return (int(sub["pair_capable"].sum()),
                int((sub["pair_capable"] & sub["any_positive"]).sum()))

    pair_total, pair_pos = pair_counts()
    if pair_pos < PAIR_POSITIVE_GOAL:
        pool = universe[universe["pair_capable"] & universe["any_positive"]]
        take("pair_positive", pool, PAIR_POSITIVE_GOAL - pair_pos)
    pair_total, _ = pair_counts()
    if pair_total < PAIR_GOAL:
        pool = universe[universe["pair_capable"]]
        take("pair_any", pool, PAIR_GOAL - pair_total,
             prefer=pool["clean_background"])

    # -- Slot 6: background spread across provinces ------------------
    bg_provinces = sorted(universe.loc[
        universe["clean_background"]
        & (universe["province"] != "UNKNOWN"), "province"].unique())

    def bg_counts() -> tuple[int, int]:
        sub = universe[universe["cell_id"].isin(ids())
                       & universe["clean_background"]]
        return len(sub), sub[sub["province"] != "UNKNOWN"][
            "province"].nunique()

    rounds = 0
    while True:
        bg_n, bg_regions = bg_counts()
        if bg_n >= BACKGROUND_GOAL and bg_regions >= BACKGROUND_REGIONS_GOAL:
            break
        progressed = False
        for prov in bg_provinces:
            pool = universe[(universe["province"] == prov)
                            & universe["clean_background"]]
            if take("background_spread", pool, 1,
                    prefer=pool["pair_capable"]):
                progressed = True
            bg_n, bg_regions = bg_counts()
            if bg_n >= BACKGROUND_GOAL and bg_regions \
                    >= BACKGROUND_REGIONS_GOAL:
                break
        rounds += 1
        if not progressed or rounds > len(bg_provinces) + BACKGROUND_GOAL:
            break
    bg_n, bg_regions = bg_counts()
    if bg_n < BACKGROUND_GOAL:
        deficits.append(
            f"background: max attainable {bg_n} < goal {BACKGROUND_GOAL}")
    if bg_regions < BACKGROUND_REGIONS_GOAL:
        deficits.append(
            f"background regions: max attainable {bg_regions} < goal "
            f"{BACKGROUND_REGIONS_GOAL}")

    # -- Slot 7: positive stratum coverage ---------------------------
    def add_coverage(slot: str, pool: pd.DataFrame) -> None:
        if len(ids()) >= MAX_NEW_CELLS:
            return
        take(slot, pool, 1, prefer=pool["pair_capable"])

    panel0 = universe[universe["cell_id"].isin(ids())]
    covered_agreement = set(panel0.loc[
        panel0["any_positive"], "agreement_2020"])
    for cat in sorted(set(universe.loc[
            universe["any_positive"], "agreement_2020"])):
        if cat not in covered_agreement:
            add_coverage(
                f"agreement_stratum:{cat}",
                universe[universe["agreement_2020"] == cat])
            panel0 = universe[universe["cell_id"].isin(ids())]
            covered_agreement = set(panel0.loc[
                panel0["any_positive"], "agreement_2020"])
    covered_area = set(panel0.loc[
        panel0["any_positive"], "area_class"])
    for cls in ("TRACE", "SMALL", "MEDIUM", "LARGE"):
        if cls not in covered_area:
            add_coverage(
                f"area_class:{cls}",
                universe[(universe["area_class"] == cls)
                         & universe["any_positive"]])
            panel0 = universe[universe["cell_id"].isin(ids())]
            covered_area = set(panel0.loc[
                panel0["any_positive"], "area_class"])

    # -- Slot 8: operational island coverage -------------------------
    island_pos = universe[universe["island"] & universe["any_positive"]]
    if not (ids() & set(island_pos["cell_id"])) and len(island_pos):
        add_coverage("island_positive", island_pos)
    island_bg = universe[universe["island"] & universe["clean_background"]]
    if not (ids() & set(island_bg["cell_id"])) and len(island_bg):
        add_coverage("island_background", island_bg)

    if len(ids()) > MAX_NEW_CELLS:
        deficits.append(
            f"quota sequence requires {len(ids())} > cap {MAX_NEW_CELLS}")

    panel_ids = sorted(ids())[:MAX_NEW_CELLS]
    panel = universe[universe["cell_id"].isin(panel_ids)].sort_values(
        "cell_id").reset_index(drop=True)
    panel["inclusion_reasons"] = panel["cell_id"].map(
        lambda c: ";".join(inclusion[c]))
    goals = _goal_attainment(panel, holdouts)
    for label, key, target in (
            ("geodata both-year positives", "n_geo_both", GEO_GOAL),
        ("geodata regions", "n_geo_both_regions", GEO_REGIONS_GOAL),
            ("cmsa both-year positives", "n_cmsa_both", CMSA_GOAL),
            ("cmsa regions", "n_cmsa_both_regions", CMSA_REGIONS_GOAL),
            ("clean background cells", "n_clean_background",
             BACKGROUND_GOAL),
            ("background regions", "n_background_regions",
             BACKGROUND_REGIONS_GOAL),
            ("pair-capable cells", "n_pair_capable", PAIR_GOAL),
            ("pair-capable positives", "n_pair_capable_positive",
             PAIR_POSITIVE_GOAL)):
        have = goals[key]
        if have < target:
            deficits.append(f"{label}: max attainable {have} < {target}")
    for prov, report in goals["holdouts"].items():
        if not report["holds"]:
            deficits.append(
                f"holdout {prov} fails its cell/positive/outside quota")
    return {
        "panel": panel,
        "holdout_provinces": holdouts,
        "inclusion": inclusion,
        "goals": goals,
        "deficits": deficits,
        "checksum": panel_checksum(panel_ids, holdouts),
    }


def _goal_attainment(panel: pd.DataFrame, holdouts: list[str]
                     ) -> dict[str, Any]:
    provinces = panel[panel["province"] != "UNKNOWN"]
    holdout_report: dict[str, dict[str, Any]] = {}
    for prov in holdouts:
        sub = panel[panel["province"] == prov]
        outside = panel[panel["province"] != prov]
        holdout_report[prov] = {
            "cells": int(len(sub)),
            "positive": int(sub["any_positive"].sum()),
            "outside_cells": int(len(outside)),
            "outside_positive": int(outside["any_positive"].sum()),
            "holds": bool(
                len(sub) >= HELD_CELLS_MIN
                and int(sub["any_positive"].sum()) >= HELD_POSITIVE_MIN
                and len(outside) >= OUTSIDE_CELLS_MIN
                and int(outside["any_positive"].sum())
                >= OUTSIDE_POSITIVE_MIN),
        }
    goals_met = bool(
        int(panel["geo_both"].sum()) >= GEO_GOAL
        and provinces.loc[provinces["geo_both"], "province"].nunique()
        >= GEO_REGIONS_GOAL
        and int(panel["cmsa_both"].sum()) >= CMSA_GOAL
        and provinces.loc[provinces["cmsa_both"], "province"].nunique()
        >= CMSA_REGIONS_GOAL
        and int(panel["clean_background"].sum()) >= BACKGROUND_GOAL
        and provinces.loc[provinces["clean_background"], "province"].nunique()
        >= BACKGROUND_REGIONS_GOAL
        and int(panel["pair_capable"].sum()) >= PAIR_GOAL
        and int((panel["pair_capable"]
                 & panel["any_positive"]).sum()) >= PAIR_POSITIVE_GOAL
        and len(holdouts) >= HOLDOUT_GOAL
        and all(h["holds"] for h in holdout_report.values()))
    return {
        "n_cells": int(len(panel)),
        "n_geo_both": int(panel["geo_both"].sum()),
        "n_geo_both_regions": int(provinces.loc[
            provinces["geo_both"], "province"].nunique()),
        "n_cmsa_both": int(panel["cmsa_both"].sum()),
        "n_cmsa_both_regions": int(provinces.loc[
            provinces["cmsa_both"], "province"].nunique()),
        "n_clean_background": int(panel["clean_background"].sum()),
        "n_background_regions": int(provinces.loc[
            provinces["clean_background"], "province"].nunique()),
        "n_pair_capable": int(panel["pair_capable"].sum()),
        "n_pair_capable_positive": int(
            (panel["pair_capable"] & panel["any_positive"]).sum()),
        "n_positive": int(panel["any_positive"].sum()),
        "n_island": int(panel["island"].sum()),
        "holdouts": holdout_report,
        "goals_met": goals_met,
    }
