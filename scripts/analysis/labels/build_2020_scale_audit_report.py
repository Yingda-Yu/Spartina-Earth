#!/usr/bin/env python3
"""Issue #18 reporting layer: tables, block-bootstrap CIs, H1-H6 evidence.

Reads the aggregate (non-pixel) CSVs written by run_2020_scale_audit.py
from work/issue18/derived and emits tracked, compact products under
datasets/manifests/2020_label_scale_audit_v1/ plus candidate figures
under docs/analysis/figures/. No product bytes are copied into Git.

Semantics reminder: every metric here describes agreement/disagreement
between external-reference products. There is no ground truth and no
accuracy claim anywhere in the output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spartina.labels import scale_agreement as sa

REPO_ROOT = Path(__file__).resolve().parents[3]
WORK = REPO_ROOT / "work/issue18"
DERIVED = WORK / "derived"
OUT = REPO_ROOT / "datasets/manifests/2020_label_scale_audit_v2"
FIG_OUT = REPO_ROOT / "docs/analysis/figures"

PAIR_DEFS_30 = (
    ("GEO_CMSA", "g", "bc", "gc", "dgc"),
    ("GEO_CMSSM", "g", "bm", "gm", "dgm"),
    ("CMSA_CMSSM", "bc", "bm", "cmb", "dcm"),
)
PAIR_DEFS_10 = (("CMSA_CMSSM", "bc", "bm", "cmb", "dcm"),)
DIST_ORDER = list(sa.DISTANCE_BIN_LABELS)
PATCH_ORDER = list(sa.PATCH_BIN_LABELS)
COVER_ORDER = list(sa.COVER_BIN_LABELS)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


_REGION = {0: "UNATTRIBUTED"}
for i, name in enumerate(
    p for p in sa.PROVINCE_ORDER if p != "UNATTRIBUTED"
):
    _REGION[i + 1] = name


@dataclass
class PairwiseRow:
    support: str
    pair: str
    region: str
    area_a_km2: float
    area_b_km2: float
    intersection_km2: float
    jaccard: float
    dice: float
    area_bias_a_minus_b: float
    omission_of_a_vs_b_km2: float
    commission_of_a_vs_b_km2: float
    binary_disagreement_fraction: float
    denominator_pixels: int
    denominator_area_km2: float
    semantics: str


def pairwise_rows(
    region: pd.DataFrame, pixel_area: float, support: str,
    pairs: tuple[tuple[str, str, str, str, str], ...],
) -> pd.DataFrame:
    rows = []
    for r in region.itertuples(index=False):
        for pair, a_col, b_col, i_col, d_col in pairs:
            area_a = float(getattr(r, a_col)) * pixel_area / 1e6
            area_b = float(getattr(r, b_col)) * pixel_area / 1e6
            inter = float(getattr(r, i_col)) * pixel_area / 1e6
            n = int(r.n)
            omission, commission = sa.omission_commission(
                area_a, area_b, inter
            )
            rows.append(PairwiseRow(
                support=support, pair=pair,
                region=_REGION.get(int(r.region), str(r.region)),
                area_a_km2=round(area_a, 4), area_b_km2=round(area_b, 4),
                intersection_km2=round(inter, 4),
                jaccard=round(sa.jaccard(inter, area_a, area_b), 4),
                dice=round(sa.dice(inter, area_a, area_b), 4),
                area_bias_a_minus_b=round(sa.area_bias(area_a, area_b), 4),
                omission_of_a_vs_b_km2=round(omission, 4),
                commission_of_a_vs_b_km2=round(commission, 4),
                binary_disagreement_fraction=(
                    round(float(getattr(r, d_col)) / n, 4) if n else float("nan")
                ),
                denominator_pixels=n,
                denominator_area_km2=round(n * pixel_area / 1e6, 3),
                semantics=(
                    "binary >=0.5 fractional-cover rule for Jaccard/Dice and "
                    "omission/commission of A vs named reference B; "
                    "denominator footprint = all core pixels of blocks that "
                    "intersect any mapped feature (full core, patch "
                    "interiors included); boundary- and patch-stratified "
                    "tables use the 300 m edge band"
                ),
            ))
    return pd.DataFrame([vars(x) for x in rows])


def block_bootstrap_dice(
    cells: pd.DataFrame, pairs: tuple[tuple[str, str, str, str, str], ...],
    domain_variant: str,
) -> pd.DataFrame:
    """Cluster bootstrap of the POOLED binary Dice over W10 cell blocks.

    Each resample draws W10 cells with replacement (seed 20201018, 500
    resamples), sums the two binary areas and their intersection across
    the drawn cells, and forms 2*sum(I)/sum(A+B). Pixels are never
    treated as independent; cells with no mapped area enter with zeros.
    ``domain_variant`` is KEEP_ONLY (3,011 cells) or
    KEEP_PLUS_PROVISIONAL (3,021); each variant is resampled within its
    own universe with the same seed.
    """
    n_cells = int(len(cells))
    rng = np.random.default_rng(20201018)
    draws = rng.integers(0, n_cells, size=(500, n_cells))
    rows = []
    for pair, a_col, b_col, i_col, _d_col in pairs:
        a = cells[a_col].to_numpy(dtype=np.float64)
        b = cells[b_col].to_numpy(dtype=np.float64)
        i = cells[i_col].to_numpy(dtype=np.float64)
        point = float(2.0 * i.sum() / (a.sum() + b.sum()))
        boots = []
        for take in draws:
            denom = a[take].sum() + b[take].sum()
            boots.append(
                float(2.0 * i[take].sum() / denom) if denom else np.nan
            )
        lo, hi = np.nanquantile(boots, 0.025), np.nanquantile(boots, 0.975)
        rows.append({
            "pair": pair,
            "domain_variant": domain_variant,
            "spatial_blocks": n_cells,
            "pooled_dice": round(point, 4),
            "ci95_low": round(float(lo), 4),
            "ci95_high": round(float(hi), 4),
            "bootstrap": (
                "W10-cell cluster bootstrap of pooled Dice, percentile, "
                "500 resamples, seed 20201018; "
                f"domain universe {domain_variant} ({n_cells} cells)"
            ),
        })
    return pd.DataFrame(rows)


def boundary_table(distance: pd.DataFrame, pixel_area: float,
                   support: str,
                   pairs: tuple[tuple[str, str, str, str, str], ...]) -> pd.DataFrame:
    rows = []
    for r in distance.itertuples(index=False):
        for pair, _a, _b, _i, d_col in pairs:
            n = int(r.n)
            rows.append({
                "support": support, "pair": pair,
                "region": _REGION.get(int(r.region), str(r.region)),
                "distance_to_nearest_mapped_boundary_m": r.dist_bin,
                "denominator_pixels": n,
                "binary_disagreement_fraction": round(
                    float(getattr(r, d_col)) / n, 4
                ) if n else float("nan"),
                "band_area_km2": round(n * pixel_area / 1e6, 4),
            })
    out = pd.DataFrame(rows)
    out["distance_to_nearest_mapped_boundary_m"] = pd.Categorical(
        out["distance_to_nearest_mapped_boundary_m"], DIST_ORDER, ordered=True
    )
    return out


def patch_class_table(frame: pd.DataFrame, support: str,
                      has_geo: bool) -> pd.DataFrame:
    rows = []
    for r in frame.itertuples(index=False):
        n = int(r.n)
        row = {
            "support": support,
            "region": _REGION.get(int(r.region), str(r.region)),
            "cmsa_patch_size_class": r.patch_c_bin,
            "cmssm_patch_size_class": r.patch_m_bin,
            "denominator_pixels": n,
            "d_cmsa_cmssm_fraction": round(float(r.dcm) / n, 4) if n else float("nan"),
        }
        if has_geo:
            row["d_geo_cmsa_fraction"] = (
                round(float(r.dgc) / n, 4) if n else float("nan")
            )
            row["d_geo_cmssm_fraction"] = (
                round(float(r.dgm) / n, 4) if n else float("nan")
            )
        rows.append(row)
    return pd.DataFrame(rows)


def small_patch_omission(patches: pd.DataFrame) -> pd.DataFrame:
    """H3: coverage of each fine patch by the coarser/other products."""
    frame = patches.copy()
    frame["patch_size_class"] = frame["patch_area_m2"].apply(
        lambda a: sa.assign_bin(float(a), sa.PATCH_BIN_EDGES, sa.PATCH_BIN_LABELS)
    )
    frame["geodata_fraction"] = (
        frame["geodata_cover_m2"] / frame["own_intersect_m2"]
    ).clip(upper=1.0)
    frame["other_fine_fraction"] = (
        frame["other_fine_fractional_m2"] / frame["own_intersect_m2"]
    ).clip(upper=1.0)
    grouped = frame.groupby(
        ["support", "product", "patch_size_class"], observed=True
    )
    out = grouped.agg(
        n_patches=("patch_id", "count"),
        total_patch_area_km2=("patch_area_m2", lambda s: s.sum() / 1e6),
        median_geodata_fraction=("geodata_fraction", "median"),
        zero_geodata_patch_fraction=(
            "geodata_fraction", lambda s: float((s <= 0.001).mean())
        ),
        median_other_fine_fraction=("other_fine_fraction", "median"),
        zero_other_fine_patch_fraction=(
            "other_fine_fraction", lambda s: float((s <= 0.001).mean())
        ),
    ).reset_index()
    num_cols = [c for c in out.columns if c.endswith("fraction") or "median" in c]
    out[num_cols] = out[num_cols].round(4)
    return out


def occupancy_distribution(contingency: pd.DataFrame) -> pd.DataFrame:
    """H6: distribution of fine fractional occupancy inside GEO classes."""
    rows = []
    total = contingency.groupby(["g_class"])["n"].sum()
    for g_class in (0, 1):
        tot = float(total.get(g_class, 0.0))
        for fine, col in (("CMSA", "cover_c_bin"), ("CMSSM", "cover_m_bin")):
            sub = contingency.groupby(["g_class", col])["n"].sum()
            for bin_label in COVER_ORDER:
                count = float(sub.get((g_class, bin_label), 0.0))
                rows.append({
                    "geodata_class": int(g_class),
                    "fine_product": fine,
                    "fine_occupancy_bin": bin_label,
                    "pixel_count": int(count),
                    "fraction_within_geodata_class": (
                        round(count / tot, 5) if tot else float("nan")
                    ),
                })
    return pd.DataFrame(rows)


def fractional_table(
    cells30: pd.DataFrame, cells10: pd.DataFrame,
    r30: pd.DataFrame, r10: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fractional-cover relationships on explicit supports.

    Pixel arrays are never treated as independent: correlations are
    computed across W10 spatial blocks (cell-mean fractions), exactly
    the coarse contextual role Issue #18 assigns to W10 cells.
    """
    from scipy.stats import spearmanr

    rows = []
    for region_id, grp in r30.groupby("region"):
        grp = grp.iloc[0]
        n = int(grp.n)
        rows.append({
            "support": "30m_GEODATA_native_grid",
            "region": _REGION.get(int(region_id), str(region_id)),
            "mean_geo_binary": round(float(grp.g) / n, 4),
            "mean_cmsa_cover": round(float(grp.c) / n, 4),
            "mean_cmssm_cover": round(float(grp.m) / n, 4),
            "mean_cover_diff_cmsa_minus_geo": round(
                (float(grp.c) - float(grp.g)) / n, 4
            ),
            "mean_cover_diff_cmssm_minus_geo": round(
                (float(grp.m) - float(grp.g)) / n, 4
            ),
            "mean_cover_diff_cmsa_minus_cmssm": round(
                (float(grp.c) - float(grp.m)) / n, 4
            ),
            "denominator_pixels": n,
        })
    for region_id, grp in r10.groupby("region"):
        grp = grp.iloc[0]
        n = int(grp.n)
        rows.append({
            "support": "10m_project_lattice",
            "region": _REGION.get(int(region_id), str(region_id)),
            "mean_geo_binary": float("nan"),
            "mean_cmsa_cover": round(float(grp.c) / n, 4),
            "mean_cmssm_cover": round(float(grp.m) / n, 4),
            "mean_cover_diff_cmsa_minus_geo": float("nan"),
            "mean_cover_diff_cmssm_minus_geo": float("nan"),
            "mean_cover_diff_cmsa_minus_cmssm": round(
                (float(grp.c) - float(grp.m)) / n, 4
            ),
            "denominator_pixels": n,
        })

    block_rows = []

    def block_corr(frame: pd.DataFrame, support: str, pixel_area: float) -> None:
        d = frame[frame.n > 0].copy()
        pairs = (("geo_cmsa", "g", "c"), ("geo_cmssm", "g", "m"),
                 ("cmsa_cmssm", "c", "m"))
        rng = np.random.default_rng(20201018)
        for label, a, b in pairs:
            xa = d[a] / d["n"]
            xb = d[b] / d["n"]
            rho = float(spearmanr(xa, xb).statistic)
            boots = []
            for _ in range(500):
                take = rng.integers(0, len(d), len(d))
                boots.append(float(spearmanr(xa.to_numpy()[take],
                                             xb.to_numpy()[take]).statistic))
            block_rows.append({
                "support": support,
                "fractional_cover_pair": label,
                "w10_block_spearman_rho": round(rho, 4),
                "ci95_low": round(float(np.quantile(boots, 0.025)), 4),
                "ci95_high": round(float(np.quantile(boots, 0.975)), 4),
                "spatial_blocks": int(len(d)),
                "context_note": (
                    f"W10-cell-mean fractional cover; contextual only "
                    f"(pixel area {pixel_area:.0f} m2)"
                ),
            })

    block_corr(cells30, "30m_GEODATA_native_grid", 900.0)
    d10 = cells10[cells10.n > 0].copy()
    rho = float(spearmanr(d10["c"] / d10["n"], d10["m"] / d10["n"]).statistic)
    rng = np.random.default_rng(20201018)
    xa, xb = d10["c"] / d10["n"], d10["m"] / d10["n"]
    boots = [
        float(spearmanr(
            xa.to_numpy()[idx], xb.to_numpy()[idx]
        ).statistic)
        for idx in (rng.integers(0, len(d10), len(d10)) for _ in range(500))
    ]
    block_rows.append({
        "support": "10m_project_lattice",
        "fractional_cover_pair": "cmsa_cmssm",
        "w10_block_spearman_rho": round(rho, 4),
        "ci95_low": round(float(np.quantile(boots, 0.025)), 4),
        "ci95_high": round(float(np.quantile(boots, 0.975)), 4),
        "spatial_blocks": int(len(d10)),
        "context_note": "W10-cell-mean fractional cover; contextual only (100 m2)",
    })
    return pd.DataFrame(rows), pd.DataFrame(block_rows)


def domain_summary(cells30: pd.DataFrame) -> pd.DataFrame:
    """Explicit domain accounting (Issue #18 section E)."""
    membership = pd.read_csv(
        REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
    )
    cells = pd.read_csv(REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv")
    cells = cells.merge(membership[["cell_id", "membership_v1_candidate"]],
                        on="cell_id", how="left")
    keep_statuses = (
        "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL",
        "PROVISIONAL_UNRESOLVED",
    )
    # cell_idx in the derived tables enumerates the filtered, ordered
    # domain frame exactly as the runner builds it; filter BEFORE the
    # positional index is assigned.
    cells = cells[cells.membership_v1_candidate.isin(keep_statuses)].reset_index(drop=True)
    cells["cell_idx"] = np.arange(len(cells))
    joined = cells30.merge(
        cells[["cell_idx", "membership_v1_candidate"]], on="cell_idx", how="left"
    )
    rows = []
    counts = membership["membership_v1_candidate"].value_counts().to_dict()
    for status in (
        "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL",
        "PROVISIONAL_UNRESOLVED", "EXCLUDE_DOMAIN_ARTIFACT",
    ):
        rows.append({
            "membership_status": status,
            "n_cells_total": int(counts.get(status, 0)),
            "n_cells_with_30m_core_pixels": int(
                (joined.membership_v1_candidate == status).sum()
            ),
            "geodata_area_km2": round(
                float(joined.loc[joined.membership_v1_candidate == status, "g"].sum())
                * 900 / 1e6, 3
            ),
            "cmsa_fractional_area_km2": round(
                float(joined.loc[joined.membership_v1_candidate == status, "c"].sum())
                * 900 / 1e6, 3
            ),
            "cmssm_fractional_area_km2": round(
                float(joined.loc[joined.membership_v1_candidate == status, "m"].sum())
                * 900 / 1e6, 3
            ),
            "note": (
                "Full-core per-cell areas on the 30 m GEODATA grid; "
                "PROVISIONAL cells are the 10 Issue #17 cells pending owner "
                "sign-off; EXCLUDE cells never enter analysis (no pixels "
                "rasterized); OUTSIDE cells are outside the frozen 25 km "
                "coastal band and are not part of the candidate manifest"
            ),
        })
    return pd.DataFrame(rows)


def hypothesis_evidence(
    pw30: pd.DataFrame, pw10: pd.DataFrame, b30: pd.DataFrame, b10: pd.DataFrame,
    region30: pd.DataFrame, omission: pd.DataFrame, occ: pd.DataFrame,
    boot_by_variant: dict[str, pd.DataFrame],
    pw30_product: pd.DataFrame | None = None,
    region_attribution: str = "product-derived patch ownership (v1)",
) -> dict[str, Any]:
    """Apply the pre-registered H1-H6 decision rules (Issue #18 wording).

    The preregistered hypotheses are unchanged in R1; H4 is evaluated on
    the source-independent region attribution when supplied, with the
    v1 product-derived ranges retained for comparison.
    """
    national = pw30.groupby("pair", as_index=False).agg(
        area_a_km2=("area_a_km2", "sum"),
        area_b_km2=("area_b_km2", "sum"),
        intersection_km2=("intersection_km2", "sum"),
        denom=("denominator_pixels", "sum"),
    )

    # H1: boundary stratification, national pooling by distance band.
    def band_fraction(frame: pd.DataFrame, pair: str, band: str) -> float:
        sub = frame[frame.pair == pair].copy()
        sub["band"] = sub[
            "distance_to_nearest_mapped_boundary_m"
        ].astype(str)
        grouped = sub.groupby("band", observed=True)
        num = grouped.apply(
            lambda g: (
                g["binary_disagreement_fraction"]
                * g["denominator_pixels"]
            ).sum(),
            include_groups=False,
        )
        den = grouped["denominator_pixels"].sum()
        if band not in den.index or float(den.loc[band]) == 0.0:
            return float("nan")
        return float(num.loc[band] / den.loc[band])

    h1_pairs = {}
    for pair in ("GEO_CMSA", "GEO_CMSSM", "CMSA_CMSSM"):
        near = band_fraction(b30, pair, "0-30m")
        far = band_fraction(b30, pair, "120-300m")
        h1_pairs[pair] = {"near_0_30": round(near, 4), "far_120_300": round(far, 4),
                          "ratio": round(near / far, 2) if far else None}
    h1_supported = all(v["ratio"] is not None and v["ratio"] > 1.2
                       for v in h1_pairs.values())

    # H2: disagreement rises when the OTHER product's patch is small.
    pc = region30.copy()
    small = pc[pc.patch_m_bin.isin(["100-900m2", "900-2500m2"])]
    large = pc[pc.patch_m_bin == ">=1e5m2"]

    def discord(frame: pd.DataFrame) -> float:
        n = frame["n"].sum()
        return float(frame["dcm"].sum() / n) if n else float("nan")

    h2_small, h2_large = discord(small), discord(large)
    h2_supported = bool(np.isfinite(h2_small) and h2_small > 1.2 * h2_large)

    # H3: small fine patches omitted by the coarse product.
    om30 = omission[omission.support == "30m"]
    h3 = {}
    for product in ("cmsa", "cmssm"):
        sub = om30[om30["product"] == product].set_index("patch_size_class")
        h3[product] = {
            "small_zero_geodata_fraction_100_900m2": (
                float(sub.loc["100-900m2", "zero_geodata_patch_fraction"])
                if "100-900m2" in sub.index else None
            ),
            "large_zero_geodata_fraction_1e5plus": (
                float(sub.loc[">=1e5m2", "zero_geodata_patch_fraction"])
                if ">=1e5m2" in sub.index else None
            ),
        }
    h3_supported = all(
        v["small_zero_geodata_fraction_100_900m2"] is not None
        and v["large_zero_geodata_fraction_1e5plus"] is not None
        and v["small_zero_geodata_fraction_100_900m2"]
        > v["large_zero_geodata_fraction_1e5plus"]
        for v in h3.values()
    )

    # H4: regional spread of binary Dice (R1: independent attribution).
    def dice_ranges(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
        out = {}
        for pair in ("GEO_CMSA", "GEO_CMSSM", "CMSA_CMSSM"):
            vals = frame[
                (frame.pair == pair) & (frame.region != "UNATTRIBUTED")
            ]
            vals = vals[vals.denominator_pixels > 0]
            out[pair] = {
                "min": float(vals.dice.min()), "max": float(vals.dice.max()),
                "range": round(float(vals.dice.max() - vals.dice.min()), 3),
                "n_regions": int(vals.region.nunique()),
            }
        return out

    dice_spread = dice_ranges(pw30)
    h4_supported = all(v["range"] >= 0.10 for v in dice_spread.values())
    dice_spread_product = (
        dice_ranges(pw30_product) if pw30_product is not None else None
    )
    h4_product_supported = (
        all(v["range"] >= 0.10 for v in dice_spread_product.values())
        if dice_spread_product is not None else None
    )

    # H5: area totals close while patch overlap much lower.
    def nat_pair(pair: str) -> pd.Series:
        return national[national.pair == pair].iloc[0]
    gc = nat_pair("GEO_CMSA")
    area_bias = abs(gc.area_a_km2 - gc.area_b_km2) / gc.area_b_km2
    nat_dice = sa.dice(
        gc.intersection_km2, gc.area_a_km2, gc.area_b_km2
    )
    h5_supported = bool(area_bias < 0.20 and nat_dice < 0.70)

    # H6: discordant 30 m calls frequently sit on mixed occupancy.
    occ_pivot = occ.pivot_table(
        index=["fine_product", "geodata_class"],
        columns="fine_occupancy_bin", values="fraction_within_geodata_class",
        aggfunc="first",
    )
    h6 = {}
    for fine in ("CMSA", "CMSSM"):
        g1 = occ_pivot.loc[(fine, 1)]
        g0 = occ_pivot.loc[(fine, 0)]
        # Occupancy bins are pre-registered at 0.25/0.5/0.75; "mixed" is
        # reported both narrowly (0.25-0.75) and via the sub-50% share.
        h6[fine] = {
            "geo1_fine_mixed_0.25_0.75_fraction": round(
                float(g1.get("(0.25,0.5]", 0.0) + g1.get("(0.5,0.75]", 0.0)),
                4,
            ),
            "geo1_fine_below_half": round(
                float(g1.get("0", 0.0) + g1.get("(0,0.25]", 0.0)
                      + g1.get("(0.25,0.5]", 0.0)), 4
            ),
            "geo0_fine_above_half": round(
                float(g0.get("(0.5,0.75]", 0.0) + g0.get("(0.75,1]", 0.0)), 4
            ),
        }
    # A binary-vs-mixed tension is present if a material share of GEO=1
    # pixels carries only sub-50% fine occupancy.
    h6_supported = all(v["geo1_fine_below_half"] >= 0.05 for v in h6.values())

    def verdict(flag: bool) -> str:
        return "SUPPORTED" if flag else "NOT_SUPPORTED"

    return {
        "decision_rule_version": (
            "issue18-hypotheses-v1; rules fixed before reading results; "
            "distance/cover bin edges are right-inclusive (30 m lattice "
            "ring belongs to 0-30m on both supports)"
        ),
        "H1_boundary_effect": {
            "verdict": verdict(h1_supported),
            "rule": "all three pairs: near(0-30 m) disagreement > 1.2x far(120-300 m)",
            "by_pair": h1_pairs,
        },
        "H2_patch_size_effect": {
            "verdict": "SUPPORTED" if h2_supported else "NOT_SUPPORTED",
            "rule": "CMSA-CMSSM discordance in CMSSM <2500 m2 patch pixels "
                    "> 1.2x that in >=1e5 m2 patch pixels",
            "small_patch_discordance": round(h2_small, 4),
            "large_patch_discordance": round(h2_large, 4),
            "observed_direction": (
                "same_as_preregistered_expectation" if h2_supported
                else "opposite_to_preregistered_expectation"
            ),
            "interpretation": (
                "H2 is NOT_SUPPORTED: the observed direction was opposite "
                "to the preregistered expectation - overall CMSA-CMSSM "
                "discordance conditional on small CM-SSM patch-size strata "
                f"({round(h2_small, 4)}) was lower than in the >=1e5 m2 "
                f"stratum ({round(h2_large, 4)}). This is a directional "
                "non-support statement about one conditional estimand, not "
                "a claim that the patch-size hypothesis is universally "
                "falsified."
                if not h2_supported else
                "Discordance was higher in the small-patch stratum as "
                "preregistered."
            ),
            "h2_vs_h3_distinction": (
                "H2 and H3 are not contradictory. H2 is an overall CMSA vs "
                "CM-SSM discordance rate CONDITIONAL ON CM-SSM patch-size "
                "strata (denominator = 300 m band pixels in each stratum). "
                "H3 is a different estimand: the fraction of FINE-REFERENCE "
                "patches that receive zero cover from the COARSE product, "
                "compared by patch size (denominator = fine patches). "
                "Coarse products can omit many small fine patches (H3 "
                "supported) while the two fine products still agree more, "
                "not less, where small patches occur (H2 not supported)."
            ),
        },
        "H3_coarse_small_patch_omission": {
            "verdict": verdict(h3_supported),
            "rule": "zero-GEODATA fraction of 100-900 m2 fine patches exceeds "
                    "that of >=1e5 m2 patches for both fine products",
            "by_product": h3,
        },
        "H4_regional_effect": {
            "verdict": verdict(h4_supported),
            "rule": "regional binary Dice range >= 0.10 for every pair",
            "region_attribution": region_attribution,
            "by_pair": dice_spread,
            "product_derived_v1_comparison": (
                {
                    "by_pair": dice_spread_product,
                    "verdict": verdict(bool(h4_product_supported)),
                    "note": (
                        "v1 product-derived region labels (patch ownership); "
                        "retained for the before/after attribution audit"
                    ),
                }
                if dice_spread_product is not None else None
            ),
        },
        "H5_area_vs_patch_agreement": {
            "verdict": verdict(h5_supported),
            "rule": "GEO-vs-CMSA national |area bias| < 20% while national "
                    "binary Dice < 0.70",
            "area_bias": round(float(area_bias), 4),
            "national_binary_dice": round(float(nat_dice), 4),
        },
        "H6_binary_mixed_pixel": {
            "verdict": verdict(h6_supported),
            "rule": ">=5% of GEO=1 pixels carry <50% fine occupancy for both "
                    "fine products (binary labelling hides mixed support)",
            "by_product": h6,
        },
        "block_bootstrap_national_dice": {
            variant: frame.to_dict(orient="records")
            for variant, frame in boot_by_variant.items()
        },
        "domain_variant_policy": (
            "KEEP_ONLY (3,011 owner-signed cells) is the primary result; "
            "KEEP_PLUS_PROVISIONAL (3,021 cells, ten Issue #17 cells "
            "without owner sign-off) is reported as sensitivity only"
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    FIG_OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((WORK / "transform_manifest.json").read_text())

    r30 = pd.read_csv(DERIVED / "s30_region.csv")
    d30 = pd.read_csv(DERIVED / "s30_distance.csv")
    p30 = pd.read_csv(DERIVED / "s30_patch_class.csv")
    c30 = pd.read_csv(DERIVED / "s30_contingency.csv")
    pc30 = pd.read_csv(DERIVED / "s30_patch_cover.csv")
    cells30 = pd.read_csv(DERIVED / "s30_cells.csv")
    r10 = pd.read_csv(DERIVED / "s10_region.csv")
    d10 = pd.read_csv(DERIVED / "s10_distance.csv")
    p10 = pd.read_csv(DERIVED / "s10_patch_class.csv")
    pc10 = pd.read_csv(DERIVED / "s10_patch_cover.csv")
    cells10 = pd.read_csv(DERIVED / "s10_cells.csv")

    # Issue #18 R1 Part A: source-independent region attribution
    # (Natural Earth admin-1), present when the runner was invoked with
    # --independent-regions. Regional tables then key on those codes;
    # the product-derived region tables remain for before/after audit.
    indep_enabled = bool(
        manifest.get("independent_region_attribution", {}).get("enabled")
    )
    ri30 = pd.read_csv(DERIVED / "s30_region_independent.csv") if (
        DERIVED / "s30_region_independent.csv"
    ).exists() else None
    ri10 = pd.read_csv(DERIVED / "s10_region_independent.csv") if (
        DERIVED / "s10_region_independent.csv"
    ).exists() else None
    attr30 = pd.read_csv(DERIVED / "s30_region_attribution.csv") if (
        DERIVED / "s30_region_attribution.csv"
    ).exists() else None
    attr10 = pd.read_csv(DERIVED / "s10_region_attribution.csv") if (
        DERIVED / "s10_region_attribution.csv"
    ).exists() else None
    valid30 = pd.read_csv(DERIVED / "s30_region_validation.csv") if (
        DERIVED / "s30_region_validation.csv"
    ).exists() else None
    valid10 = pd.read_csv(DERIVED / "s10_region_validation.csv") if (
        DERIVED / "s10_region_validation.csv"
    ).exists() else None
    indep_label = (
        "independent Natural Earth 10m admin-1 v5.1.1 "
        "(centroid-in-province; else nearest province <=25 km with "
        ">300 m second-province margin; else UNKNOWN)"
        if indep_enabled else
        "product-derived patch ownership (v1)"
    )

    # Complete W10 domain universe: the runner only emits cells that
    # intersect a processed block. Empty cells are real spatial blocks
    # and must enter the cluster bootstrap and block correlations as
    # zero rows so the resampling distribution is not biased toward
    # occupied cells.
    membership = pd.read_csv(
        REPO_ROOT / "datasets/manifests/china_coastal_cells_v1_candidate.csv"
    )
    domain_cells = pd.read_csv(
        REPO_ROOT / "work/national/domain/cells_china_albers_W10000.csv"
    ).merge(
        membership[["cell_id", "membership_v1_candidate"]],
        on="cell_id", how="left",
    )
    domain_cells = domain_cells[
        domain_cells.membership_v1_candidate.isin((
            "KEEP_MAINLAND_COASTAL", "KEEP_ISLAND_COASTAL",
            "PROVISIONAL_UNRESOLVED",
        ))
    ].reset_index(drop=True)
    domain_cells["cell_idx"] = np.arange(len(domain_cells))
    n_domain = int(len(domain_cells))
    n_keep = int(
        sa.domain_variant_mask(
            domain_cells.membership_v1_candidate, False
        ).sum()
    )
    n_prov = n_domain - n_keep

    def complete_universe(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.set_index("cell_idx").reindex(np.arange(n_domain))
        num_cols = [
            c for c in out.columns
            if out[c].dtype.kind in "iuf" and c != "cell_idx"
        ]
        out[num_cols] = out[num_cols].fillna(0.0)
        out = out.reset_index(names="cell_idx")
        return out.merge(
            domain_cells[["cell_idx", "membership_v1_candidate"]],
            on="cell_idx", how="left",
        )

    cells30_full = complete_universe(cells30)
    cells10_full = complete_universe(cells10)

    def variant_slice(frame: pd.DataFrame, include_provisional: bool) -> pd.DataFrame:
        mask = sa.domain_variant_mask(
            frame.membership_v1_candidate, include_provisional
        )
        return frame.loc[mask].reset_index(drop=True)

    variants = (
        ("KEEP_ONLY", False),
        ("KEEP_PLUS_PROVISIONAL", True),
    )
    cells30_variant = {
        name: variant_slice(cells30_full, inc) for name, inc in variants
    }
    cells10_variant = {
        name: variant_slice(cells10_full, inc) for name, inc in variants
    }

    # 1. National / regional mapped area.
    area_rows = []
    for prod, col in (("geodata", "g"), ("cmsa", "c"), ("cmssm", "m")):
        area_rows.append({
            "product": prod,
            "support": "30m_GEODATA_native_grid",
            "semantics": ("binary pixel count" if prod == "geodata"
                          else "sum of exact fractional cover per 30 m pixel"),
            "mapped_area_km2": round(
                float(r30[col].sum()) * 900.0 / 1e6, 4
            ),
        })
    for prod, col in (("cmsa", "c"), ("cmssm", "m")):
        area_rows.append({
            "product": prod,
            "support": "10m_project_lattice",
            "semantics": "sum of exact fractional cover per 10 m pixel",
            "mapped_area_km2": round(
                float(r10[col].sum()) * 100.0 / 1e6, 4
            ),
        })
    for prod, key in (
        ("geodata", "geodata"),
        ("cmsa", "cmsa_gridcode2_utm_repaired"),
        ("cmssm", "cmssm_utm_repaired"),
    ):
        area_rows.append({
            "product": prod,
            "support": "native",
            "semantics": (
                "uint8==1 pixel count x 900 m2"
                if prod == "geodata"
                else "planar polygon area, EPSG:32650, repaired derived copy"
            ),
            "mapped_area_km2": manifest["native_area_km2"][key],
        })
    area = pd.DataFrame(area_rows)
    area.to_csv(OUT / "table1_mapped_area.csv", index=False)

    # 2. Pairwise agreement. R1 primary region keying is the
    # source-independent attribution; product-derived v1 keying is
    # retained for the before/after comparison only.
    pw30_product = pairwise_rows(
        r30, 900.0, "30m_GEODATA_native_grid", PAIR_DEFS_30
    )
    pw10_product = pairwise_rows(
        r10, 100.0, "10m_project_lattice", PAIR_DEFS_10
    )
    pw30 = (
        pairwise_rows(ri30, 900.0, "30m_GEODATA_native_grid", PAIR_DEFS_30)
        if ri30 is not None else pw30_product
    )
    pw10 = (
        pairwise_rows(ri10, 100.0, "10m_project_lattice", PAIR_DEFS_10)
        if ri10 is not None else pw10_product
    )
    pw30["region_attribution"] = indep_label
    pw10["region_attribution"] = indep_label
    pw = pd.concat([pw30, pw10], ignore_index=True)
    pw.to_csv(OUT / "table2_pairwise_agreement_by_region.csv", index=False)

    # Table 11: before/after attribution comparison per region & pair.
    def attribution_comparison(
        main: pd.DataFrame, prod: pd.DataFrame
    ) -> pd.DataFrame:
        cols = ["support", "pair", "region"]
        a = main[cols + [
            "area_a_km2", "area_b_km2", "intersection_km2", "dice",
        ]].rename(columns={
            "area_a_km2": "area_a_independent_km2",
            "area_b_km2": "area_b_independent_km2",
            "intersection_km2": "intersection_independent_km2",
            "dice": "dice_independent",
        })
        b = prod[cols + [
            "area_a_km2", "area_b_km2", "intersection_km2", "dice",
        ]].rename(columns={
            "area_a_km2": "area_a_product_derived_km2",
            "area_b_km2": "area_b_product_derived_km2",
            "intersection_km2": "intersection_product_derived_km2",
            "dice": "dice_product_derived",
        })
        out = a.merge(b, on=cols, how="outer")
        out["dice_delta_independent_minus_product"] = (
            out.dice_independent - out.dice_product_derived
        ).round(4)
        return out

    comp = pd.concat(
        [attribution_comparison(pw30, pw30_product),
         attribution_comparison(pw10, pw10_product)],
        ignore_index=True,
    )
    comp.to_csv(OUT / "table11_region_attribution_comparison.csv",
                index=False)

    # Bootstrap for BOTH domain variants (KEEP_ONLY is primary).
    boot_parts = []
    for variant, _inc in variants:
        b30v = block_bootstrap_dice(
            cells30_variant[variant], PAIR_DEFS_30, variant
        )
        b10v = block_bootstrap_dice(
            cells10_variant[variant], PAIR_DEFS_10, variant
        )
        b30v["support"] = "30m_GEODATA_native_grid"
        b10v["support"] = "10m_project_lattice"
        boot_parts.extend([b30v, b10v])
    boot = pd.concat(boot_parts, ignore_index=True)
    boot.to_csv(OUT / "table3_block_bootstrap_dice.csv", index=False)

    # 3. Boundary / patch stratification.
    b30 = boundary_table(d30, 900.0, "30m_GEODATA_native_grid", PAIR_DEFS_30)
    b10 = boundary_table(d10, 100.0, "10m_project_lattice", PAIR_DEFS_10)
    pd.concat([b30, b10], ignore_index=True).to_csv(
        OUT / "table4_boundary_distance_disagreement.csv", index=False
    )
    pc30_tbl = patch_class_table(p30, "30m_GEODATA_native_grid", has_geo=True)
    pc10_tbl = patch_class_table(p10, "10m_project_lattice", has_geo=False)
    pc30_tbl.to_csv(
        OUT / "table5_patch_size_disagreement_30m.csv", index=False
    )
    pc10_tbl.to_csv(
        OUT / "table5_patch_size_disagreement_10m.csv", index=False
    )

    # 4. Patch-level omission / occupancy.
    patches = pd.concat([pc30, pc10], ignore_index=True)
    omission = small_patch_omission(patches)
    omission.to_csv(OUT / "table6_patch_omission_by_size.csv", index=False)
    occ = occupancy_distribution(c30)
    occ.to_csv(OUT / "table7_coarse_pixel_occupancy.csv", index=False)

    # 5b. Fractional-cover relationships and domain accounting.
    # Regional means are attribution-based; block correlations are
    # membership-sensitive, so they are computed per domain variant.
    frac_regions, fb_keep = fractional_table(
        cells30_variant["KEEP_ONLY"], cells10_variant["KEEP_ONLY"],
        ri30 if ri30 is not None else r30,
        ri10 if ri10 is not None else r10,
    )
    _fr, fb_prov = fractional_table(
        cells30_variant["KEEP_PLUS_PROVISIONAL"],
        cells10_variant["KEEP_PLUS_PROVISIONAL"],
        ri30 if ri30 is not None else r30,
        ri10 if ri10 is not None else r10,
    )
    fb_keep["domain_variant"] = "KEEP_ONLY"
    fb_prov["domain_variant"] = "KEEP_PLUS_PROVISIONAL"
    frac_regions.to_csv(
        OUT / "table8_fractional_cover_by_region.csv", index=False
    )
    frac_blocks = pd.concat([fb_keep, fb_prov], ignore_index=True)
    frac_blocks.to_csv(
        OUT / "table9_w10_block_fractional_correlation.csv", index=False
    )
    domain = domain_summary(
        cells30_full.drop(columns=["membership_v1_candidate"])
    )
    domain.to_csv(OUT / "table10_domain_accounting.csv", index=False)

    # Table 12: independent attribution method ledger.
    if attr30 is not None and attr10 is not None:
        method_rows = []
        method_names = {
            1: "CENTROID_IN_PROVINCE",
            2: "NEAREST_PROVINCE_WITHIN_25KM",
            0: "UNKNOWN_OFFSHORE_OR_BORDER_TIE",
        }

        def method_rows_for(
            frame: pd.DataFrame, support: str, pixel_area: float,
            fields: tuple[str, ...],
        ) -> list[dict[str, Any]]:
            rows = []
            total = float(frame.pixels.sum())
            for rr in frame.itertuples(index=False):
                row = {
                    "support": support,
                    "method": method_names.get(int(rr.method), str(rr.method)),
                    "region": _REGION.get(int(rr.region), str(rr.region)),
                    "labelled_pixels": int(rr.pixels),
                    "fraction_of_labelled_pixels": (
                        round(float(rr.pixels) / total, 6) if total else float("nan")
                    ),
                }
                for fld in fields:
                    row[f"{fld}_area_km2"] = round(
                        float(getattr(rr, fld)) * pixel_area / 1e6, 4
                    )
                rows.append(row)
            return rows

        method_rows += method_rows_for(attr30, "30m", 900.0, ("g", "bc", "bm"))
        method_rows += method_rows_for(attr10, "10m", 100.0, ("bc", "bm"))
        pd.DataFrame(method_rows).to_csv(
            OUT / "table12_region_attribution_method.csv", index=False
        )

        # Table 13: product-derived vs independent region crosswalk.
        def crosswalk(
            frame: pd.DataFrame, support: str
        ) -> pd.DataFrame:
            out = frame.copy()
            out["support"] = support
            out["prod_region_name"] = out.prod_region.map(_REGION)
            out["indep_region_name"] = out.indep_region.map(_REGION)
            if "fine_agree" not in out.columns:
                out["fine_agree"] = np.nan
                out["fine_pixels"] = out["pixels"]
            for col in ("g", "bc", "bm"):
                if col not in out.columns:
                    out[col] = np.nan
            return out[[
                "support", "prod_region", "prod_region_name",
                "indep_region", "indep_region_name", "pixels",
                "g", "bc", "bm", "fine_pixels", "fine_agree",
            ]]

        pd.concat(
            [crosswalk(valid30, "30m"), crosswalk(valid10, "10m")],
            ignore_index=True,
        ).to_csv(OUT / "table13_region_crosswalk_validation.csv",
                 index=False)

    # Table 14: KEEP_ONLY vs KEEP_PLUS_PROVISIONAL sensitivity.
    sens_rows = []
    for support, pairs30 in (
        ("30m_GEODATA_native_grid", PAIR_DEFS_30),
        ("10m_project_lattice", PAIR_DEFS_10),
    ):
        for pair, *_ in pairs30:
            ko = boot[
                (boot.support == support) & (boot.pair == pair)
                & (boot.domain_variant == "KEEP_ONLY")
            ].iloc[0]
            kp = boot[
                (boot.support == support) & (boot.pair == pair)
                & (boot.domain_variant == "KEEP_PLUS_PROVISIONAL")
            ].iloc[0]
            delta = float(kp.pooled_dice) - float(ko.pooled_dice)
            sens_rows.append({
                "metric": "pooled_binary_dice",
                "support": support,
                "pair": pair,
                "keep_only_value": ko.pooled_dice,
                "keep_only_ci95": f"[{ko.ci95_low},{ko.ci95_high}]",
                "keep_only_blocks": int(ko.spatial_blocks),
                "keep_plus_provisional_value": kp.pooled_dice,
                "keep_plus_provisional_ci95": f"[{kp.ci95_low},{kp.ci95_high}]",
                "keep_plus_provisional_blocks": int(kp.spatial_blocks),
                "absolute_delta": round(delta, 4),
                "relative_delta_pct": round(
                    100.0 * delta / float(ko.pooled_dice), 3
                ),
            })
    # Spearman block-correlation sensitivity.
    for rr in fb_keep.itertuples(index=False):
        kp = fb_prov[
            (fb_prov.support == rr.support)
            & (fb_prov.fractional_cover_pair == rr.fractional_cover_pair)
        ].iloc[0]
        delta = float(kp.w10_block_spearman_rho) - float(rr.w10_block_spearman_rho)
        sens_rows.append({
            "metric": "w10_block_spearman_rho",
            "support": rr.support,
            "pair": rr.fractional_cover_pair,
            "keep_only_value": rr.w10_block_spearman_rho,
            "keep_only_ci95": f"[{rr.ci95_low},{rr.ci95_high}]",
            "keep_only_blocks": int(rr.spatial_blocks),
            "keep_plus_provisional_value": kp.w10_block_spearman_rho,
            "keep_plus_provisional_ci95": f"[{kp.ci95_low},{kp.ci95_high}]",
            "keep_plus_provisional_blocks": int(kp.spatial_blocks),
            "absolute_delta": round(delta, 4),
            "relative_delta_pct": (
                round(100.0 * delta / float(rr.w10_block_spearman_rho), 3)
                if float(rr.w10_block_spearman_rho) else float("nan")
            ),
        })
    sens = pd.DataFrame(sens_rows)
    sens.to_csv(OUT / "table14_domain_membership_sensitivity.csv",
                index=False)

    # 5. Hypotheses.
    evidence = hypothesis_evidence(
        pw30, pw10, b30, b10, p30, omission, occ,
        {v: boot[boot.domain_variant == v].drop(columns="domain_variant")
         for v, _ in variants},
        pw30_product=pw30_product if ri30 is not None else None,
        region_attribution=indep_label,
    )
    evidence["domain_universe"] = {
        "KEEP_ONLY_cells": n_keep,
        "KEEP_PLUS_PROVISIONAL_cells": n_domain,
        "provisional_cells_pending_owner_signoff": n_prov,
        "primary_manuscript_variant": "KEEP_ONLY",
    }
    (OUT / "hypothesis_evidence_v2.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
    )

    # 6. Result manifest with checksums.
    tracked = sorted(OUT.glob("*"))
    result_manifest = {
        "title": "2020 multi-resolution label disagreement and scale audit",
        "version": "v2 (Issue #18 R1 scientific closure)",
        "issue": 18,
        "supersedes": (
            "datasets/manifests/2020_label_scale_audit_v1/ (frozen; "
            "v1 tables retained for traceability, not deleted)"
        ),
        "r1_changes": {
            "A_region_attribution": (
                "source-independent Natural Earth admin-1 attribution "
                "replaces product-derived region keys in all regional "
                "tables; UNKNOWN pixels retained as region 0"
                if indep_enabled else
                "independent attribution disabled in this run"
            ),
            "B_domain_sensitivity": (
                "KEEP_ONLY 3,011-cell universe is primary; "
                "KEEP_PLUS_PROVISIONAL 3,021 cells reported as "
                "sensitivity (tables 3, 9, 14)"
            ),
            "C_h2_language": (
                "H2 reported as NOT_SUPPORTED with observed-direction "
                "statement; H2/H3 estimand distinction recorded"
            ),
        },
        "git_commit": manifest["git_commit"],
        "generated_from": (
            "scripts/analysis/labels/run_2020_scale_audit.py and "
            "scripts/analysis/labels/build_2020_scale_audit_report.py"
        ),
        "input_manifest": (
            "work/issue18/transform_manifest.json (gitignored bytes; "
            "input checksums recorded there)"
        ),
        "outputs": {p.name: sha256(p) for p in tracked},
        "terminology_policy": (
            "agreement/disagreement/external-reference agreement only; "
            "no accuracy claims (GOLD=0)"
        ),
        "statistics_policy": (
            "W10-cell spatial block bootstrap; effect sizes reported; "
            "pixel-level N never used as independent sample count; "
            "primary inference restricted to KEEP_ONLY 3,011 cells"
        ),
        "independent_region_attribution": manifest.get(
            "independent_region_attribution", {"enabled": False}
        ),
    }
    (OUT / "result_manifest.json").write_text(
        json.dumps(result_manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(evidence, indent=2, ensure_ascii=False)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
