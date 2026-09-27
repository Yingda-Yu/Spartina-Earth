"""M1.5 Pilot-0 baseline ladder: torch-dependent contract tests.

Covers IGNORE/WEAK exclusion, silver_strict behaviour, deterministic
augmentation, variant channel ordering, pretrained channel inflation,
training-side TEST denial, run registry completeness.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("pandas")
pytest.importorskip("rasterio")
pytest.importorskip("segmentation_models_pytorch")
pytest.importorskip("transformers")

from spartina.data.dataset import (  # noqa: E402
    Pilot0WindowDataset,
    geometric_transform,
    grid_view_masks,
    prepare_grid,
    view_masks,
)
from spartina.data.normalization import compute_band_stats  # noqa: E402
from spartina.data.pilot0 import VARIANT_BANDS, Pilot0Sources  # noqa: E402
from spartina.experiments import embargo as embargo_mod  # noqa: E402
from spartina.experiments.registry import (  # noqa: E402
    REGISTRY_COLUMNS,
    RunContext,
    append_registry_row,
)
from spartina.models.baselines.inflation import inflate_kernel  # noqa: E402

PATCH = 96


def make_sources() -> Pilot0Sources:
    rng = np.random.default_rng(11)
    h = w = 240
    stack = rng.normal(0.0, 1.0, (11, h, w)).astype(np.float32)
    silver = np.zeros((h, w), dtype=bool)
    weak = np.zeros((h, w), dtype=bool)
    ignore = np.zeros((h, w), dtype=bool)
    silver[10:20, 10:20] = True
    weak[10:20, 10:20] = True          # agreement silver+weak
    weak[40:46, 40:46] = True          # WEAK-only disagreement
    ignore[80:84, 80:84] = True        # IGNORE region
    weak_only = weak & ~silver & ~ignore
    rows = []
    for split, c0 in (("train", 0), ("train", 48), ("val", 96),
                      ("val", 144), ("test", 144)):
        rows.append({"tile_id": f"{split}-{c0}", "split": split,
                     "row_off": 0, "col_off": c0, "height": PATCH,
                     "width": PATCH})
    windows = pd.DataFrame(rows)
    return Pilot0Sources(
        stack=stack, weak=weak, silver=silver, ignore=ignore,
        weak_only=weak_only, windows=windows, crs="EPSG:32651",
        transform=(30, 0, 0, 0, -30, 0), stack_checksum="synth",
        root=Path("."))


@pytest.fixture(scope="module")
def env():
    sources = make_sources()
    stats = compute_band_stats(
        sources.stack, np.ones((sources.height, sources.width), bool),
        0.005, 0.995)
    grid = prepare_grid(sources, stats)
    gate = embargo_mod.EmbargoGate(None, "s1", "n1")
    return sources, grid, gate


# ------------------------------------------------------------- label views

def test_ignore_pixels_excluded_from_both_views(env) -> None:
    sources, grid, _ = env
    views = grid_view_masks(sources, grid, "full")
    r, c = 81, 81
    assert sources.ignore[r, c]
    assert not views["arbitrated_core"][r, c]
    assert not views["silver_strict"][r, c]


def test_weak_only_pixels_excluded_from_core_not_silent_background(
        env) -> None:
    sources, _, _ = env
    valid = np.ones_like(sources.silver)
    views = view_masks(valid, sources.silver, sources.weak,
                       sources.ignore, sources.weak_only)
    r, c = 42, 42
    assert sources.weak[r, c] and not sources.silver[r, c]
    # excluded from primary loss; NEVER silently used as background
    assert not views["arbitrated_core"][r, c]
    # still tracked in the diagnostic weak-only mask
    assert views["weak_only"][r, c]


def test_silver_strict_treats_weak_only_as_background(env) -> None:
    sources, _, _ = env
    valid = np.ones_like(sources.silver)
    views = view_masks(valid, sources.silver, sources.weak,
                       sources.ignore, sources.weak_only)
    r, c = 42, 42
    assert views["silver_strict"][r, c]      # evaluated
    assert not sources.silver[r, c]          # target = background


# ----------------------------------------------------------- augmentation

def test_augmentation_deterministic(env) -> None:
    sources, grid, gate = env
    d1 = Pilot0WindowDataset(sources, grid, "full", "train", gate,
                             train=True, base_seed=42, epoch=3)
    d2 = Pilot0WindowDataset(sources, grid, "full", "train", gate,
                             train=True, base_seed=42, epoch=3)
    kinds = {d1._kind_for(i) for i in range(200)}
    assert kinds <= set(range(6))
    assert kinds != {0}
    i1, i2 = d1[1], d2[1]
    assert i1["aug_kind"] == i2["aug_kind"]
    torch.testing.assert_close(i1["x"], i2["x"])
    base = Pilot0WindowDataset(sources, grid, "full", "val", gate,
                               train=False)
    bx = base[0]["x"]
    # explicit geometric transform agrees with manual horizontal flip
    xt, _ = geometric_transform(bx.numpy(), {"m": np.ones((96, 96))}, 1)
    np.testing.assert_array_equal(xt, np.ascontiguousarray(
        bx.numpy()[:, :, ::-1]))


# ------------------------------------------------------------- channel order

def test_variant_channel_ordering(env) -> None:
    sources, grid, gate = env
    for variant, bands in VARIANT_BANDS.items():
        ds = Pilot0WindowDataset(sources, grid, variant, "val", gate,
                                 train=False)
        item = ds[0]
        row = ds.rows.iloc[0]
        r0, c0 = int(row["row_off"]), int(row["col_off"])
        expect = grid.norm[bands][:, r0:r0 + PATCH, c0:c0 + PATCH]
        np.testing.assert_allclose(item["x"].numpy(), expect)
        assert item["x"].shape[0] == len(bands)


# ------------------------------------------------------------- inflation

def test_pretrained_channel_inflation_mean_rgb_rule() -> None:
    rgb = torch.arange(2 * 3 * 5 * 5, dtype=torch.float32).reshape(
        2, 3, 5, 5)
    for c in (7, 9, 11):
        w = inflate_kernel(rgb, c)
        assert w.shape == (2, c, 5, 5)
        mean = rgb.mean(dim=1, keepdim=True)
        expected = mean.repeat(1, c, 1, 1) * (3.0 / c)
        torch.testing.assert_close(w, expected)


# ------------------------------------------------------------- registry

def test_run_registry_completeness(tmp_path) -> None:
    repo = tmp_path
    ctx = RunContext(
        repo=repo, runs_root=repo / "runs/pilot0",
        registry_dir=repo / "docs/experiments/registries",
        model="unet", variant="optical", seed=17).initialize()
    info = ctx.save_checkpoint(
        {"model_state": {"a": torch.zeros(3)}})
    ctx.manifest.update({
        "training": {"best_epoch": 4}, "val_threshold": 0.31,
        "val_core_iou": 0.5, "checkpoint_sha256": info["checkpoint_sha256"],
        "checkpoint_size_bytes": info["checkpoint_size_bytes"],
        "efficiency": {"train_wall_s": 12.3},
        "gpu": {"id": 1, "model": "RTX3090", "vram_mib": 24268,
                "driver": "535"}})
    ctx.finalize("COMPLETED")
    append_registry_row(repo, ctx.registry_dir, ctx.manifest)
    csv_path = ctx.registry_dir / "pilot0_registry.csv"
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == set(REGISTRY_COLUMNS)
    for col in ("run_id", "model", "variant", "seed", "status",
                "checkpoint_sha256", "val_threshold", "gpu_id"):
        assert row[col] not in ("", "None"), col
    assert (ctx.run_dir / "run_manifest.json").exists()


def test_training_side_gate_denies_test_even_unlocked(env, monkeypatch) -> None:
    from spartina.training.engine import _NoTestGate
    monkeypatch.setenv(embargo_mod.ALLOW_TEST_ENV, "1")
    g = _NoTestGate()
    assert g.request_split("train") is None
    with pytest.raises(embargo_mod.TestEmbargoError):
        g.request_split("test")
