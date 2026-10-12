"""Phase A support inventory for SpartinaShift-Silver v0.1 (Issue #20).

Pure, I/O-free logic. The builder script
(``scripts/benchmarks/spartinashift/build_support_matrix_v0_1.py``)
loads the frozen Issue #19 V2 manifests and calls :func:`build_support_matrix`
and :func:`task_support_summary`.

Semantics carried forward from the Issue #19 frozen policy:

* every label is a SILVER occupancy summary; ``GOLD = 0``;
* GEODATA backgrounds are WEAK negatives only, never verified
  ecological negatives (``SOURCE_BACKGROUND``);
* CMSA / CM-SSM are positive-only products: uncovered pixels and
  gridcode-0 regions stay UNKNOWN;
* CM-SSM 2020 is ``EXTERNAL_REFERENCE_ONLY`` (source license conflict):
  it never trains, never validates, and is never tuned against -- only
  named, held-out cross-source agreement evaluation;
* 30 m labels are never rasterised onto a 10 m support. All Stage-1
  tasks analyse on the 30 m label grid; native 10 m EO is aggregated
  down to that grid. The CM-SSM 10 m support is recorded for
  evaluation-only sensitivity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

#: All Stage-1 tasks analyse on the native 30 m SILVER label grid.
ANALYSIS_GRID_M: Final[int] = 30

#: Issue #19 V2 actual-mask landing gate (fraction of pixel centres
#: observed inside the W10 Albers cell). Landed == passed.
ACTUAL_MASK_GATE: Final[float] = 0.95

#: Support-only adequacy thresholds for province holdouts (Phase A
#: inventory rule; no model performance is inspected to set these).
REGION_HOLDOUT_MIN_CELLS: Final[int] = 4
REGION_TRAIN_MIN_CELLS: Final[int] = 8

OPTICAL: Final[str] = "optical"
SAR: Final[str] = "sar"

RIGHTS_GEODATA: Final[str] = (
    "SILVER_TRAINING_ELIGIBLE_INTERNAL_RESEARCH_ONLY")
RIGHTS_CMSA: Final[str] = "SILVER_TRAINING_ELIGIBLE_NONCOMMERCIAL"
RIGHTS_CMSSM: Final[str] = (
    "EXTERNAL_REFERENCE_ONLY_SOURCE_LICENSE_CONFLICT")


@dataclass(frozen=True)
class SensorInfo:
    """Static EO sensor description."""

    modality: str
    native_res_m: int
    family: str


SENSOR_INFO: Final[dict[str, SensorInfo]] = {
    "landsat5": SensorInfo(OPTICAL, 30, "landsat"),
    "landsat7": SensorInfo(OPTICAL, 30, "landsat"),
    "landsat8": SensorInfo(OPTICAL, 30, "landsat"),
    "sentinel2": SensorInfo(OPTICAL, 10, "sentinel"),
    "sentinel1": SensorInfo(SAR, 10, "sentinel"),
}


@dataclass(frozen=True)
class RightsPolicy:
    """Training/evaluation rights for one label source key."""

    rights_status: str
    training_eligible: bool
    evaluation_eligible: bool
    external_reference_only: bool
    note: str


def _rights_table() -> dict[str, RightsPolicy]:
    table: dict[str, RightsPolicy] = {}
    for year in (1990, 2000, 2015, 2020):
        table[f"GEODATA_{year}"] = RightsPolicy(
            RIGHTS_GEODATA, True, True, False,
            "internal non-commercial research only; no redistribution; "
            "source identity preserved; report as agreement/reproduction")
    for year in range(2017, 2022):
        table[f"CMSA_{year}"] = RightsPolicy(
            RIGHTS_CMSA, True, True, False,
            "CC-BY-NC-4.0 attribution NESDC + Li/Tian/Li 2024; "
            "non-commercial; only years with paired landed EO may "
            "actually enter training")
    table["CM-SSM_2020"] = RightsPolicy(
        RIGHTS_CMSSM, False, True, True,
        "SOURCE_LICENSE_CONFLICT; never train/validate/tune; named "
        "held-out external-reference agreement evaluation only")
    return table


RIGHTS_BY_SOURCE_KEY: Final[dict[str, RightsPolicy]] = _rights_table()

PAIRED_LANDED: Final[str] = "PAIRED_LANDED"
EO_PLANNED_NOT_LANDED: Final[str] = "EO_PLANNED_NOT_LANDED"
EO_UNPLANNED: Final[str] = "EO_UNPLANNED"

MATRIX_COLUMNS: Final[list[str]] = [
    "cell_id",
    "region_province",
    "coastal_segment",
    "year",
    "label_source_key",
    "label_family",
    "label_year",
    "label_support_m",
    "label_kind",
    "gold_available",
    "rights_status",
    "training_eligible",
    "evaluation_eligible",
    "external_reference_only",
    "rights_note",
    "sensor",
    "modality",
    "eo_variant",
    "product_id",
    "event_id",
    "event_utc",
    "eo_native_res_m",
    "eo_qa_verdict",
    "actual_mask_gate",
    "actual_observed_fraction",
    "actual_mask_gate_pass",
    "analysis_grid_m",
    "eo_to_analysis_grid",
    "n_pure_positive_px",
    "n_mixed_px",
    "n_pure_negative_weak_px",
    "n_unknown_px",
    "n_label_px",
    "positive_area_km2_in_cell",
    "has_pure_positive",
    "has_mixed",
    "has_weak_background",
    "cmssm_10m_support_available",
    "pairing_state",
    "missing_state",
    "unlanded_reason",
    "label_tif_sha256",
]


def _label_kind(family: str) -> str:
    return "BINARY_RASTER" if family == "GEODATA" else "POSITIVE_POLYGONS"


def _compatible_sensors(support_m: int) -> set[str]:
    """Sensors that can feed an analysis grid at ``support_m``.

    30 m SILVER labels accept every sensor (30 m native Landsat and 10 m
    Sentinel EO aggregated down). The 10 m CM-SSM support accepts native
    10 m Sentinel EO only (Landsat is never upsampled).
    """
    if support_m == 30:
        return set(SENSOR_INFO)
    if support_m == 10:
        return {"sentinel1", "sentinel2"}
    raise ValueError(f"unsupported support_m {support_m}")


def _eo_to_analysis(native_m: int, analysis_m: int) -> str:
    if native_m == analysis_m:
        return f"NATIVE_{native_m}M"
    if native_m < analysis_m:
        return (
            f"VALID_PIXEL_AGGREGATE_{native_m}M_TO_{analysis_m}M"
            "_TRAIN_ONLY_FROM_FROZEN_RULE")
    raise ValueError(
        f"refuse to upsample {native_m} m EO to {analysis_m} m grid")


def build_support_matrix(
    plan: pd.DataFrame,
    landed: pd.DataFrame,
    labels: pd.DataFrame,
    panel: pd.DataFrame,
    rejected_product_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Build the cell x year x sensor x label-source support matrix.

    Nothing is silently dropped: planned-but-unlanded EO appears as
    :data:`EO_PLANNED_NOT_LANDED` rows and label sources with no EO
    plan appear as :data:`EO_UNPLANNED` rows.
    """
    region = panel.set_index("cell_id")
    landed_by_cell_year: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for rec in landed.to_dict("records"):
        landed_by_cell_year.setdefault(
            (str(rec["cell_id"]), int(rec["year"])), []).append(rec)
    plan_by_cell_year: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for rec in plan.to_dict("records"):
        plan_by_cell_year.setdefault(
            (str(rec["cell_id"]), int(rec["year"])), []).append(rec)

    rejected = rejected_product_ids or set()
    cmssm10_cells = {
        str(r.cell_id)
        for r in labels.itertuples()
        if str(r.family) == "CM-SSM" and int(r.support_m) == 10
    }

    rows: list[dict[str, Any]] = []
    for lab in labels.sort_values(
            ["cell_id", "family", "year", "support_m"]).to_dict("records"):
        cell = str(lab["cell_id"])
        family = str(lab["family"])
        year = int(lab["year"])
        support_m = int(lab["support_m"])
        source_key = f"{family}_{year}"
        rights = RIGHTS_BY_SOURCE_KEY[source_key]
        info = region.loc[cell]
        compatible = _compatible_sensors(support_m)
        landed_here = {
            str(rec["product_id"]): rec
            for rec in landed_by_cell_year.get((cell, year), [])
            if str(rec["sensor"]) in compatible}
        planned_here = sorted(
            (rec for rec in plan_by_cell_year.get((cell, year), [])
             if str(rec["sensor"]) in compatible),
            key=lambda r: str(r["product_id"]))
        planned_pids = {str(pl["product_id"]) for pl in planned_here}
        orphans = sorted(
            set(landed_here) - planned_pids)
        if orphans:
            raise ValueError(
                f"landed products absent from V2 plan: {sorted(orphans)}")
        if planned_here:
            for pl in planned_here:
                pid = str(pl["product_id"])
                sensor = str(pl["sensor"])
                sinfo = SENSOR_INFO[sensor]
                resampling = _eo_to_analysis(
                    sinfo.native_res_m,
                    support_m if support_m == ANALYSIS_GRID_M else 10)
                if pid in landed_here:
                    eo = landed_here[pid]
                    rows.append(_row(
                        cell, info, year, source_key, family, support_m,
                        rights, lab, cmssm10_cells, sensor=sensor,
                        variant=str(eo.get("variant", "")),
                        product_id=pid,
                        event_id=str(eo.get("event_id", "")),
                        event_utc=str(eo.get("event_utc", "")),
                        verdict=str(eo["verdict"]),
                        observed=float(eo["actual_observed_fraction"]),
                        pairing=PAIRED_LANDED, missing="OK", reason="",
                        resampling=resampling))
                else:
                    if pid in rejected:
                        status = "CONFIRMED_ACTUAL_MASK_REJECTION"
                        missing = (
                            "MISSING_EO: CONFIRMED actual-mask rejection "
                            f"(in-cell observed fraction < "
                            f"{ACTUAL_MASK_GATE:g})")
                    else:
                        status = str(pl["status"])
                        missing = f"MISSING_EO: {status}"
                    rows.append(_row(
                        cell, info, year, source_key, family, support_m,
                        rights, lab, cmssm10_cells, sensor=sensor,
                        variant=str(pl.get("variant", "")),
                        product_id=pid,
                        event_id=str(pl.get("event_id", "")),
                        event_utc=str(pl.get("event_utc", "")),
                        verdict="UNLANDED", observed=float("nan"),
                        pairing=EO_PLANNED_NOT_LANDED,
                        missing=missing, reason=status,
                        resampling=resampling))
        else:
            rows.append(_row(
                cell, info, year, source_key, family, support_m,
                rights, lab, cmssm10_cells, sensor="MISSING_EO",
                variant="", product_id="", event_id="", event_utc="",
                verdict="UNPLANNED", observed=float("nan"),
                pairing=EO_UNPLANNED,
                missing="MISSING_EO: no acquisition planned in V2 plan",
                reason="EO_UNPLANNED", resampling="NONE"))
    matrix = pd.DataFrame(rows, columns=MATRIX_COLUMNS)
    return matrix.sort_values(
        ["cell_id", "year", "label_family", "label_support_m",
         "sensor", "eo_variant"]).reset_index(drop=True)


def _row(
    cell: str,
    info: Any,
    year: int,
    source_key: str,
    family: str,
    support_m: int,
    rights: RightsPolicy,
    lab: dict[str, Any],
    cmssm10_cells: set[str],
    *,
    sensor: str,
    variant: str,
    product_id: str,
    event_id: str,
    event_utc: str,
    verdict: str,
    observed: float,
    pairing: str,
    missing: str,
    reason: str,
    resampling: str,
) -> dict[str, Any]:
    sinfo = SENSOR_INFO.get(sensor)
    gate_pass = (
        pairing == PAIRED_LANDED
        and observed >= ACTUAL_MASK_GATE)
    return {
        "cell_id": cell,
        "region_province": str(info["region_province"]),
        "coastal_segment": str(info["coastal_segment"]),
        "year": year,
        "label_source_key": source_key,
        "label_family": family,
        "label_year": year,
        "label_support_m": support_m,
        "label_kind": _label_kind(family),
        "gold_available": 0,
        "rights_status": rights.rights_status,
        "training_eligible": rights.training_eligible,
        "evaluation_eligible": rights.evaluation_eligible,
        "external_reference_only": rights.external_reference_only,
        "rights_note": rights.note,
        "sensor": sensor,
        "modality": sinfo.modality if sinfo else "none",
        "eo_variant": variant,
        "product_id": product_id,
        "event_id": event_id,
        "event_utc": event_utc,
        "eo_native_res_m": sinfo.native_res_m if sinfo else 0,
        "eo_qa_verdict": verdict,
        "actual_mask_gate": ACTUAL_MASK_GATE,
        "actual_observed_fraction": observed,
        "actual_mask_gate_pass": bool(gate_pass),
        "analysis_grid_m": (
            support_m if support_m != ANALYSIS_GRID_M
            else ANALYSIS_GRID_M),
        "eo_to_analysis_grid": resampling,
        "n_pure_positive_px": int(lab["n_pure_positive"]),
        "n_mixed_px": int(lab["n_mixed"]),
        "n_pure_negative_weak_px": int(lab["n_pure_negative"]),
        "n_unknown_px": int(lab["n_unknown"]),
        "n_label_px": int(lab["n_total"]),
        "positive_area_km2_in_cell": float(
            lab.get("positive_area_km2_in_cell",
                    lab.get("positive_area_km2", 0.0))),
        "has_pure_positive": int(lab["n_pure_positive"]) > 0,
        "has_mixed": int(lab["n_mixed"]) > 0,
        "has_weak_background": int(lab["n_pure_negative"]) > 0,
        "cmssm_10m_support_available": cell in cmssm10_cells,
        "pairing_state": pairing,
        "missing_state": missing,
        "unlanded_reason": reason,
        "label_tif_sha256": str(lab.get("tif_sha256", "")),
    }


def _paired_cells(
    matrix: pd.DataFrame,
    *,
    sensor: str,
    year: int,
    family: str,
    variant: str | None = None,
) -> list[str]:
    d = matrix[
        (matrix["pairing_state"] == PAIRED_LANDED)
        & (matrix["sensor"] == sensor)
        & (matrix["year"] == year)
        & (matrix["label_family"] == family)
        & (matrix["label_support_m"] == ANALYSIS_GRID_M)]
    if variant is not None:
        d = d[d["eo_variant"] == variant]
    return sorted(set(d["cell_id"]))


def _province_counts(cells: list[str], matrix: pd.DataFrame) -> dict[str, int]:
    if not cells:
        return {}
    sub = matrix[matrix["cell_id"].isin(cells)]
    counts = sub.groupby("region_province")["cell_id"].nunique()
    return {str(k): int(v) for k, v in sorted(counts.items())}


def _label_totals(
    matrix: pd.DataFrame, cells: list[str], source_key: str,
) -> dict[str, object]:
    d = matrix[
        matrix["cell_id"].isin(cells)
        & (matrix["label_source_key"] == source_key)
        & (matrix["label_support_m"] == ANALYSIS_GRID_M)]
    d = d.drop_duplicates(subset=["cell_id", "label_source_key"])
    return {
        "cells": len(cells),
        "pure_positive_px": int(d["n_pure_positive_px"].sum()),
        "mixed_px": int(d["n_mixed_px"].sum()),
        "weak_background_px": int(d["n_pure_negative_weak_px"].sum()),
        "unknown_px": int(d["n_unknown_px"].sum()),
        "label_px": int(d["n_label_px"].sum()),
        "positive_area_km2_sum": round(
            float(d["positive_area_km2_in_cell"].sum()), 4),
    }


def _variant_gap(
    matrix: pd.DataFrame, cells: list[str], variant: str,
) -> dict[str, int]:
    """Per-cell |S2 - S1| acquisition-date gap for one S1 variant."""
    gaps: dict[str, int] = {}
    for cell in cells:
        s2 = matrix[
            (matrix["cell_id"] == cell)
            & (matrix["year"] == 2020)
            & (matrix["sensor"] == "sentinel2")
            & (matrix["pairing_state"] == PAIRED_LANDED)
            & (matrix["label_family"] == "CMSA")
            & (matrix["label_support_m"] == ANALYSIS_GRID_M)][
                "event_utc"]
        s1 = matrix[
            (matrix["cell_id"] == cell)
            & (matrix["year"] == 2020)
            & (matrix["sensor"] == "sentinel1")
            & (matrix["eo_variant"] == variant)
            & (matrix["pairing_state"] == PAIRED_LANDED)
            & (matrix["label_family"] == "CMSA")
            & (matrix["label_support_m"] == ANALYSIS_GRID_M)][
                "event_utc"]
        if len(s2) and len(s1):
            d2 = pd.Timestamp(str(s2.iloc[0]))
            d1 = pd.Timestamp(str(s1.iloc[0]))
            gaps[cell] = int(abs((d2 - d1).days))
    return dict(sorted(gaps.items()))


def _gap_stats(gaps: dict[str, int]) -> dict[str, Any]:
    values = list(gaps.values())
    if not values:
        return {"status": "NO_PAIRED_CELLS"}
    return {
        "min_days": min(values),
        "median_days": int(pd.Series(values).median()),
        "max_days": max(values),
        "n_cells_le_3_days": sum(g <= 3 for g in values),
        "n_cells_le_7_days": sum(g <= 7 for g in values),
        "n_cells_le_14_days": sum(g <= 14 for g in values),
        "n_cells_le_30_days": sum(g <= 30 for g in values),
        "n_cells_gt_30_days": sum(g > 30 for g in values),
        "same_season_window": "autumn DOY 260-320 selection window",
        "observations_are_never_simultaneous": True,
        "threshold_frozen_in_phase_b": True,
        "gap_threshold_note": (
            "counts describe support only; the C5 pairing rule and the "
            "INSUFFICIENT_SUPPORT threshold are frozen in Phase B before "
            "any model output exists"),
    }


def task_support_summary(matrix: pd.DataFrame) -> dict[str, Any]:
    """Task-specific C1-C5 support counts, computed before any split."""
    l8_2015 = _paired_cells(
        matrix, sensor="landsat8", year=2015, family="GEODATA")
    l8_2020 = _paired_cells(
        matrix, sensor="landsat8", year=2020, family="GEODATA")
    c1_cells = sorted(set(l8_2015) & set(l8_2020))
    s2_2020 = _paired_cells(
        matrix, sensor="sentinel2", year=2020, family="CMSA")
    s2_2021 = _paired_cells(
        matrix, sensor="sentinel2", year=2021, family="CMSA")
    c2_cells = sorted(set(s2_2020) & set(s2_2021))
    l8_2020_any = _paired_cells(
        matrix, sensor="landsat8", year=2020, family="CMSA")
    s1a_2020 = _paired_cells(
        matrix, sensor="sentinel1", year=2020, family="CMSA",
        variant="A")
    s1d_2020 = _paired_cells(
        matrix, sensor="sentinel1", year=2020, family="CMSA",
        variant="D")
    c5_cells = sorted(set(s2_2020) & set(s1a_2020))
    c4_cells = sorted(set(s2_2020) | set(l8_2020_any))
    cmssm_cells = sorted(set(matrix[
        (matrix["label_family"] == "CM-SSM")
        & (matrix["year"] == 2020)
        & (matrix["label_support_m"] == 30)]["cell_id"]))

    # C3: province holdout adequacy under C1 and C2 support sets.
    c1_prov = _province_counts(c1_cells, matrix)
    c2_prov = _province_counts(c2_cells, matrix)
    regions: dict[str, dict[str, Any]] = {}
    for prov in sorted(set(c1_prov) | set(c2_prov)):
        n_c1 = c1_prov.get(prov, 0)
        n_c2 = c2_prov.get(prov, 0)
        entry: dict[str, Any] = {
            "c1_holdout_cells": n_c1,
            "c1_remaining_cells": len(c1_cells) - n_c1,
            "c2_holdout_cells": n_c2,
            "c2_remaining_cells": len(c2_cells) - n_c2,
        }
        adequate: list[str] = []
        if (n_c1 >= REGION_HOLDOUT_MIN_CELLS
                and len(c1_cells) - n_c1 >= REGION_TRAIN_MIN_CELLS):
            adequate.append("C1")
        if (n_c2 >= REGION_HOLDOUT_MIN_CELLS
                and len(c2_cells) - n_c2 >= REGION_TRAIN_MIN_CELLS):
            adequate.append("C2")
        entry["adequate_holdout_under"] = adequate
        entry["adequacy_rule"] = (
            f">= {REGION_HOLDOUT_MIN_CELLS} held-out cells and >= "
            f"{REGION_TRAIN_MIN_CELLS} remaining cells")
        regions[prov] = entry

    gaps_a = _variant_gap(matrix, c5_cells, "A")
    gaps_d = _variant_gap(matrix, c5_cells, "D")
    nearest = {
        cell: min(g for g in (gaps_a.get(cell), gaps_d.get(cell))
                  if g is not None)
        for cell in c5_cells
        if gaps_a.get(cell) is not None or gaps_d.get(cell) is not None}

    unlanded = matrix[matrix["pairing_state"] != PAIRED_LANDED]
    return {
        "product": "SPARTINASHIFT_SILVER_V0_1_SUPPORT_MATRIX",
        "phase": "A_pre_split_pre_training_inventory",
        "analysis_grid_m": ANALYSIS_GRID_M,
        "actual_mask_gate": ACTUAL_MASK_GATE,
        "gold_label_cells": 0,
        "totals": {
            "n_cells": int(matrix["cell_id"].nunique()),
            "n_landed_pairings": int(
                (matrix["pairing_state"] == PAIRED_LANDED).sum()),
            "n_unlanded_planned_rows": int(
                (matrix["pairing_state"] == EO_PLANNED_NOT_LANDED).sum()),
            "n_unplanned_rows": int(
                (matrix["pairing_state"] == EO_UNPLANNED).sum()),
            "n_matrix_rows": int(len(matrix)),
            "unlanded_reasons": {
                str(k): int(v)
                for k, v in unlanded.groupby("unlanded_reason").size().items()
                if str(k)},
        },
        "tasks": {
            "C1_cross_year_geodata_l8": {
                "description": (
                    "train GEODATA 2015 / evaluate GEODATA 2020, "
                    "Landsat 8 optical, same family/sensor year shift"),
                "landsat8_2015_cells": l8_2015,
                "landsat8_2020_cells": l8_2020,
                "eligible_cells_both_years": c1_cells,
                "n_eligible_cells": len(c1_cells),
                "by_province": c1_prov,
                "label_totals_2015": _label_totals(
                    matrix, c1_cells, "GEODATA_2015"),
                "label_totals_2020": _label_totals(
                    matrix, c1_cells, "GEODATA_2020"),
            },
            "C2_cross_year_cmsa_s2": {
                "description": (
                    "train CMSA 2020 / evaluate CMSA 2021, "
                    "Sentinel-2 optical, same sensor year shift"),
                "s2_2020_cells": s2_2020,
                "s2_2021_cells": s2_2021,
                "eligible_cells_both_years": c2_cells,
                "n_eligible_cells": len(c2_cells),
                "by_province": c2_prov,
                "label_totals_2020": _label_totals(
                    matrix, c2_cells, "CMSA_2020"),
                "label_totals_2021": _label_totals(
                    matrix, c2_cells, "CMSA_2021"),
            },
            "C3_cross_region_province_holdout": {
                "description": (
                    "province-held spatial generalisation; reported on "
                    "the C1/C2 support sets; provinces failing the "
                    "support-only rule are reported as "
                    "INSUFFICIENT_SUPPORT_FOR_REGION_<name>, never run"),
                "regions": regions,
            },
            "C4_cross_source_2020": {
                "description": (
                    "train on CMSA 2020 (S2 optical); named cross-source "
                    "AGREEMENT evaluation vs GEODATA 2020 and CM-SSM 2020 "
                    "on held-out cells; CM-SSM never trained or tuned"),
                "s2_2020_cells": s2_2020,
                "landsat8_2020_cells": l8_2020_any,
                "eligible_union_cells": c4_cells,
                "n_eligible_cells": len(c4_cells),
                "cells_with_both_s2_and_l8": sorted(
                    set(s2_2020) & set(l8_2020_any)),
                "cmssm_external_reference_cells": cmssm_cells,
                "cmssm_rights": RIGHTS_CMSSM,
            },
            "C5_modality_ablation_2020": {
                "description": (
                    "S2 optical-only vs S2+S1 optical+SAR on identical "
                    "cells/patches/seeds/budget; CMSA 2020 labels"),
                "eligible_cells": c5_cells,
                "n_eligible_cells": len(c5_cells),
                "s1_primary_variant": "A",
                "s1_variant_a_cells": s1a_2020,
                "s1_variant_d_supplemental_cells": s1d_2020,
                "s2_s1a_acquisition_gap_days": gaps_a,
                "s2_s1d_acquisition_gap_days": gaps_d,
                "s2_s1_nearest_variant_gap_days": nearest,
                "gap_stats_primary_variant_a": _gap_stats(gaps_a),
                "gap_stats_nearest_variant": _gap_stats(nearest),
                "label_totals_2020": _label_totals(
                    matrix, c5_cells, "CMSA_2020"),
            },
        },
    }
