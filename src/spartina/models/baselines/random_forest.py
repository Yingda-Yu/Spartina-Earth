"""Random-forest baseline on unique TRAIN source pixels (no window dup)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier

SAI_BAND = 8


def sample_train_pixels(
    features: np.ndarray[Any, Any], y: np.ndarray[Any, Any],
    valid: np.ndarray[Any, Any], cap: int, seed: int,
) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    """Deterministic stratified subsample over valid unique pixels."""
    idx = np.flatnonzero(valid)
    yy = y.reshape(-1)[idx].astype(np.int8)
    if idx.size <= cap:
        X = features.reshape(features.shape[0], -1)[:, idx].T
        return X, yy
    rng = np.random.default_rng(seed)
    take: list[np.ndarray[Any, Any]] = []
    remaining = cap
    classes = np.unique(yy)
    for k, cls in enumerate(classes):
        pool = idx[yy == cls]
        n = cap // len(classes) if k < len(classes) - 1 else remaining
        n = min(n, pool.size)
        take.append(rng.choice(pool, size=n, replace=False))
        remaining -= n
    sel = np.concatenate(take)
    rng.shuffle(sel)
    X = features.reshape(features.shape[0], -1)[:, sel].T
    return X, y.reshape(-1)[sel].astype(np.int8)


def fit_rf(
    X: np.ndarray[Any, Any], y: np.ndarray[Any, Any], seed: int,
    cfg: dict[str, Any],
) -> RandomForestClassifier:
    rf = RandomForestClassifier(
        n_estimators=int(cfg["n_estimators"]),
        class_weight=str(cfg["class_weight"]),
        max_features=str(cfg["max_features"]),
        min_samples_leaf=int(cfg["min_samples_leaf"]),
        n_jobs=int(cfg["n_jobs"]), random_state=seed)
    rf.fit(X, y)
    return rf


def rf_predict_proba(
    rf: RandomForestClassifier, features: np.ndarray[Any, Any],
    predict_mask: np.ndarray[Any, Any],
) -> np.ndarray[Any, Any]:
    h, w = features.shape[1:]
    out = np.full((h, w), np.nan, dtype=np.float32)
    idx = np.flatnonzero(predict_mask)
    X = features.reshape(features.shape[0], -1)[:, idx].T
    probs = rf.predict_proba(X)
    pos = int(np.flatnonzero(rf.classes_ == 1)[0])
    out.reshape(-1)[idx] = probs[:, pos].astype(np.float32)
    return out
