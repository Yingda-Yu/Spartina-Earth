"""Issue #10 audit: strict table/reconciliation gates on synthetic fixtures.

These tests never touch the real (gitignored) run store. A complete
49-key synthetic run matrix is materialized in tmp_path so the happy
path and every hard-fail branch of the audit generators are exercised.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from spartina.audit.accounting import (  # noqa: E402
    ReconciliationError,
    reconcile,
)
from spartina.audit.paths import SEEDS, VARIANTS, discover  # noqa: E402
from spartina.audit.tables import (  # noqa: E402
    TableIntegrityError,
    build_audit_tables,
    canonical_hash,
)

NEURAL = ("unet", "deeplabv3plus", "segformer_b0")
ARTIFACT_KIND = {
    "unet": "torch_checkpoint",
    "deeplabv3plus": "torch_checkpoint",
    "segformer_b0": "torch_checkpoint",
    "random_forest": "random_forest_joblib",
    "sai": "spectral_rule",
}
ARTIFACT_FILE = {
    "torch_checkpoint": "best.pt",
    "random_forest_joblib": "rf.joblib",
    "spectral_rule": "rule.json",
}


def _view(iou: float) -> dict[str, Any]:
    return {
        "threshold": 0.5, "n_valid_pixels": 1000, "n_positive_pixels": 100,
        "iou": iou, "precision": 0.8, "recall": 0.7, "f1": 0.75,
        "auprc": 0.8, "bf1_30m": 0.7, "bf1_60m": 0.8,
        "pred_area_ha": 9.0, "ref_area_ha": 10.0, "abs_area_error_ha": 1.0,
        "rel_area_error": 0.1, "signed_area_bias": -0.1, "brier": 0.05,
        "ece": 0.04,
        "patch_025": {"n_ref": 1, "n_pred": 1, "n_matches": 1,
                      "patch_precision": 1.0, "patch_recall": 1.0,
                      "small_ref_count": 0, "small_patch_recall": None},
        "patch_050": {"n_ref": 1, "n_pred": 1, "n_matches": 1,
                      "patch_precision": 1.0, "patch_recall": 1.0,
                      "small_ref_count": 0, "small_patch_recall": None},
    }


def _weak_rows() -> list[dict[str, Any]]:
    return [{"component_id": f"weakcand-{i:04d}", "label_index": i,
             "component_pixels": 50, "covered_pixels": 20, "area_ha": 0.45,
             "mean_prob": 0.4, "median_prob": 0.4,
             "above_threshold_fraction": 0.6, "component_response": 1}
            for i in range(1, 8)]


def _stress(seed_iou: float) -> dict[str, Any]:
    return {drop: {"arbitrated_core": _view(seed_iou - 0.1),
                   "silver_strict": _view(seed_iou - 0.1)}
            for drop in ("indices", "sar", "sar_indices")}


def _build_matrix(root: Path) -> tuple[Path, Path, pd.DataFrame]:
    runs_dir = root / "runs"
    reg_rows: list[dict[str, Any]] = []
    lock_entries: list[dict[str, Any]] = []

    def materialize(model: str, variant: str, seed: int | None,
                    iou: float) -> None:
        rid = f"{model}_{variant}_seed-{seed or 'det'}"
        rdir = runs_dir / model / variant / (
            f"seed-{seed}" if seed is not None else "deterministic") / rid
        rdir.mkdir(parents=True)
        kind = ARTIFACT_KIND[model]
        art = rdir / ARTIFACT_FILE[kind]
        art.write_bytes(f"{rid}-bytes".encode())
        checksum = hashlib.sha256(art.read_bytes()).hexdigest()
        manifest = {
            "run_id": rid, "model": model, "variant": variant,
            "seed": seed, "phase": "official", "status": "COMPLETED",
            "run_dir": str(rdir.relative_to(root)),
            "checkpoint_sha256": checksum, "val_threshold": 0.5,
            "config_sha256": "cfg123", "git_commit": "abc",
            "split_logical_fingerprint": "sfp",
            "normalization_sha256": "norm",
            "val_core_iou": iou,
            "n_train_pixels": 1000}
        (rdir / "run_manifest.json").write_text(
            json.dumps(manifest))
        (rdir / "val_metrics.json").write_text(json.dumps(
            {"arbitrated_core": _view(iou),
             "silver_strict": _view(iou)}))
        test_payload: dict[str, Any] = {
            "arbitrated_core": _view(iou + 0.05),
            "silver_strict": _view(iou + 0.02),
            "weak_candidate_response": _weak_rows()}
        if model in NEURAL and variant == "full":
            test_payload["missing_modality_stress"] = _stress(iou)
        (rdir / "test_metrics.json").write_text(
            json.dumps(test_payload))
        reg_rows.append({"run_id": rid, "phase": "official",
                         "status": "COMPLETED"})
        lock_entries.append({
            "run_id": rid, "model": model, "variant": variant,
            "seed": seed, "run_dir": str(rdir.relative_to(root)),
            "artifact_kind": kind, "checkpoint_sha256": checksum,
            "val_threshold": 0.5, "config_sha256": "cfg123"})

    materialize("sai", "spectral_sai", None, 0.18)
    models = ("random_forest",) + NEURAL
    for mi, model in enumerate(models):
        for si, seed in enumerate(SEEDS):
            # same IoU across variants for a model/seed -> zero deltas
            iou = 0.5 + 0.01 * mi + 0.001 * si
            for variant in VARIANTS:
                materialize(model, variant, seed, iou)
    reg_csv = root / "registry.csv"
    pd.DataFrame(reg_rows).to_csv(reg_csv, index=False)
    lock = root / "lock.json"
    lock.write_text(json.dumps(
        {"status": "FROZEN", "lock_sha256": "x", "runs": lock_entries}))
    return runs_dir, lock, reg_csv


def test_full_synthetic_matrix_reconciles_and_builds_tables(
    tmp_path: Path,
) -> None:
    runs_dir, lock, reg = _build_matrix(tmp_path)
    runs = discover(runs_dir)
    rec = reconcile(runs, lock, reg)
    assert rec["n_official"] == 49
    tables = build_audit_tables(runs)
    assert len(tables.metrics) == 98
    assert len(tables.stress) == 54
    assert len(tables.weak) == 49 * 7
    # deterministic delta arithmetic: synthetic iou per cell is constant
    # offset between splits, so every delta is zero within a split
    assert (tables.deltas["delta_iou"] == 0).all()
    # means retain all three seeds; SAI stays single-run
    cell = tables.means[
        (tables.means.model == "unet")
        & (tables.means.variant == "optical")
        & (tables.means.split == "test")].iloc[0]
    assert cell["n_seeds_in_denominator"] == 3
    assert cell["collapsed_seeds"] == 0
    sai = tables.means[(tables.means.model == "sai")].iloc[0]
    assert sai["n_seeds_in_denominator"] == 1
    # canonical hash is deterministic and content-sensitive
    h1 = canonical_hash(tables.metrics)
    h2 = canonical_hash(tables.metrics.copy())
    assert h1 == h2
    assert len(h1) == 64


def test_missing_test_record_hard_fails(tmp_path: Path) -> None:
    runs_dir, lock, reg = _build_matrix(tmp_path)
    victim = next(runs_dir.rglob("test_metrics.json"))
    victim.unlink()
    runs = discover(runs_dir)
    with pytest.raises(ReconciliationError):
        reconcile(runs, lock, reg)
    with pytest.raises(TableIntegrityError):
        build_audit_tables(runs)


def test_duplicate_run_key_hard_fails(tmp_path: Path) -> None:
    runs_dir, lock, reg = _build_matrix(tmp_path)
    # copy one run tree onto another key by duplicating its manifest id
    manifests = sorted(runs_dir.rglob("run_manifest.json"))
    src = json.loads(manifests[0].read_text())
    tgt = manifests[1]
    tgt_m = json.loads(tgt.read_text())
    tgt_m["run_id"] = src["run_id"]
    tgt.write_text(json.dumps(tgt_m))
    with pytest.raises((ReconciliationError, TableIntegrityError)):
        reconcile(discover(runs_dir), lock, reg)


def test_nonofficial_run_with_test_metrics_hard_fails(
    tmp_path: Path,
) -> None:
    runs_dir, lock, reg = _build_matrix(tmp_path)
    sm_dir = runs_dir / "unet" / "optical" / "seed-17" / "smoke-run"
    sm_dir.mkdir(parents=True)
    manifest = {"run_id": "smoke-run", "model": "unet", "variant": "optical",
                "seed": 17, "phase": "smoke", "status": "SMOKE_OK",
                "run_dir": "x", "val_threshold": 0.5}
    (sm_dir / "run_manifest.json").write_text(json.dumps(manifest))
    (sm_dir / "test_metrics.json").write_text(json.dumps(
        {"arbitrated_core": _view(0.1)}))
    with pytest.raises(ReconciliationError, match="TEST metrics"):
        reconcile(discover(runs_dir), lock, reg)


def test_collapsed_runs_stay_in_denominator(tmp_path: Path) -> None:
    runs_dir, _, _ = _build_matrix(tmp_path)
    runs = discover(runs_dir)
    classes = {
        r.run_id: ("SMALL_DATA_STOCHASTIC_COLLAPSE"
                   if r.model == "segformer_b0" and r.seed == 42
                   and r.variant == "optical"
                   else "NO_COLLAPSE")
        for r in runs}
    tables = build_audit_tables(runs, classifications=classes)
    seg = tables.means[(tables.means.model == "segformer_b0")
                       & (tables.means.split == "test")]
    assert (seg["n_seeds_in_denominator"] == 3).all()
    # optical keeps its collapsed seed; other variants have none
    by_var = dict(zip(seg.variant, seg.collapsed_seeds, strict=True))
    assert by_var == {"optical": 1, "optical_indices": 0,
                      "optical_sar": 0, "full": 0}


def test_classify_collapse_categories() -> None:
    pytest.importorskip("torch")  # forensics imports torch at module load
    pytest.importorskip("segmentation_models_pytorch")
    pytest.importorskip("transformers")
    from spartina.audit.forensics import classify

    base = {"inflation_init_max_abs_err": 0.0,
            "state_dict_missing_keys": 0,
            "state_dict_unexpected_keys": 0,
            "head_is_single_class": True,
            "train_target_positive_px_in_windows": 100}
    defect = dict(base, inflation_init_max_abs_err=0.01,
                  test_recall=0.9, val_iou_best_over_epochs=0.7)
    assert classify(defect) == "IMPLEMENTATION_DEFECT"
    unstable = dict(base, test_recall=0.01, val_iou_best_over_epochs=0.1)
    assert classify(unstable) == "OPTIMIZATION_INSTABILITY"
    small = dict(base, test_recall=0.05, val_iou_best_over_epochs=0.55)
    assert classify(small) == "SMALL_DATA_STOCHASTIC_COLLAPSE"
    healthy = dict(base, test_recall=0.8, val_iou_best_over_epochs=0.6)
    assert classify(healthy) == "NO_COLLAPSE"


def test_freeze_hash_ignores_emission_timestamp() -> None:
    from spartina.audit.freeze import _hash_json

    base = {"freeze_id": "X", "git_commit": "abc",
            "fingerprints": {"a": "1", "b": "2"}}
    h1 = _hash_json({**base, "created_utc": "2026-09-30T01:00:00Z"})
    h2 = _hash_json({**base, "created_utc": "2026-09-30T02:00:00Z"})
    h3 = _hash_json({**base, "created_utc": "2026-09-30T01:00:00Z",
                     "freeze_sha256": "anything"})
    h4 = _hash_json({**base, "created_utc": "2026-09-30T01:00:00Z",
                     "git_commit": "different"})
    assert h1 == h2 == h3
    assert h4 != h1
    assert len(h1) == 64


def test_rf_positive_column_selection_follows_classes() -> None:
    import importlib.util

    pytest.importorskip("sklearn")
    from sklearn.ensemble import RandomForestClassifier

    # load the pure-sklearn RF module without executing the baselines
    # package __init__ (which pulls torch/smp, absent in minimal envs)
    rf_path = (Path(__file__).resolve().parents[2]
               / "src/spartina/models/baselines/random_forest.py")
    spec = importlib.util.spec_from_file_location(
        "pilot0_random_forest_under_test", rf_path)
    assert spec is not None and spec.loader is not None
    rf_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf_mod)
    rf_predict_proba = rf_mod.rf_predict_proba

    rng = np.random.default_rng(0)
    # (C=2, H=20, W=1): 20 pixels, 2 features
    features = rng.normal(size=(2, 20, 1)).astype("float32")
    features[0, :10, 0] += 3.0
    y = np.zeros((20,), dtype="int8")
    y[:10] = 1
    X = features.reshape(2, -1).T
    rf = RandomForestClassifier(n_estimators=10, random_state=0)
    rf.fit(X, y)
    mask = np.ones((20, 1), dtype=bool)
    probs = rf_predict_proba(rf, features, mask)
    pos = int(np.flatnonzero(rf.classes_ == 1)[0])
    expected = rf.predict_proba(X)[:, pos]
    np.testing.assert_allclose(probs.reshape(-1), expected, rtol=1e-6)
