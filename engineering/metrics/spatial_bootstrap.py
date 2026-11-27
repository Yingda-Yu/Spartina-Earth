"""Spatial cluster bootstrap for SpartinaShift metric aggregation.

Implements BENCHMARK_METRIC_SPEC.md §2: nonparametric cluster bootstrap
over spatial units (cells). Pixel-level bootstrap is forbidden — clusters
represent spatial autocorrelation.

Usage:
    from spatial_bootstrap import cluster_bootstrap_ci
    lo, hi = cluster_bootstrap_ci(per_cell_values, cell_ids, n_boot=2000,
                                  seed=2026, level=0.95)
"""
from __future__ import annotations

import numpy as np


def cluster_bootstrap_ci(
    values,
    cluster_ids,
    n_boot: int = 2000,
    seed: int = 2026,
    level: float = 0.95,
    statistic=np.mean,
):
    """Percentile confidence interval for `statistic` of `values`,
    resampling whole clusters (cells) with replacement.

    Parameters
    ----------
    values : array-like of float
        Per-observation metric values (e.g. per-cell IoU).
    cluster_ids : array-like
        Cluster label per observation. All rows sharing a cluster id are
        resampled together. Use one unique id per row for cell-level
        values.
    n_boot : int
        Number of bootstrap replicates (spec: 2000).
    seed : int
        RNG seed (spec: 2026, fixed).
    level : float
        CI level (spec: 0.95).
    statistic : callable
        Summary statistic computed on the resampled values.

    Returns
    -------
    (point_estimate, lo, hi, n_clusters)
    """
    values = np.asarray(values, dtype=float)
    cluster_ids = np.asarray(cluster_ids)
    if values.shape[0] != cluster_ids.shape[0]:
        raise ValueError("values and cluster_ids must have equal length")
    if values.size == 0:
        raise ValueError("no observations")

    unique_clusters = np.unique(cluster_ids)
    if unique_clusters.size < 2:
        raise ValueError("cluster bootstrap requires >= 2 clusters")

    # Pre-group row indices per cluster for fast resampling.
    cluster_rows = [np.flatnonzero(cluster_ids == c) for c in unique_clusters]

    rng = np.random.default_rng(seed)
    point = float(statistic(values))

    stats = np.empty(n_boot, dtype=float)
    n = unique_clusters.size
    for b in range(n_boot):
        pick = rng.integers(0, n, size=n)
        idx = np.concatenate([cluster_rows[p] for p in pick])
        stats[b] = statistic(values[idx])

    alpha = (1.0 - level) / 2.0
    lo, hi = np.percentile(stats, [100 * alpha, 100 * (1 - alpha)])
    return point, float(lo), float(hi), int(n)
