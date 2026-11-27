"""Run manifest generator tests (EXPERIMENT_EXECUTION_PLAN §4.2).

Verifies the generator rejects runs missing provenance and enforces the
GPU policy (never GPU 0, <=3 GPUs).
Run: pytest engineering/tests/test_run_manifest.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENGINEERING = os.path.join(ROOT, "engineering")
SCRIPT = os.path.join(ENGINEERING, "run_manifest", "generate_run_manifest.py")

FULL = [
    "--run-id", "r000_smoke_test",
    "--config", os.path.join(ENGINEERING, "configs", "unet_template.yaml"),
    "--dataset-manifest-sha", "a" * 64,
    "--split-id", "SPLIT_V1_test",
    "--seeds", "42,17,2026",
    "--environment", "spartina-earth",
    "--gpu-ids", "5,8",
    "--qa-ledger-ref", "benchmarks/spartinashift/v0_2_1_repair/V022_PROTOCOL_CHECKSUM.json",
    "--git-sha", "0" * 40,
]


def run_cli(extra):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    return subprocess.run(
        [sys.executable, SCRIPT, *FULL, *extra, "--out", out],
        capture_output=True, text=True, cwd=ROOT,
    ), out


def test_manifest_accepted_and_hashed():
    r, out = run_cli([])
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"manifest written: {out}" in r.stdout
    import json
    m = json.load(open(out))
    assert m["gpu_ids"] == [5, 8]
    assert m["seeds"] == [42, 17, 2026]
    assert len(m["manifest_sha256"]) == 64
    assert len(m["config_sha256"]) == 64
    os.unlink(out)


def test_manifest_rejected_missing_split():
    r, _ = run_cli(["--split-id", ""])
    assert r.returncode == 1
    assert "split_id" in r.stderr


def test_manifest_rejected_gpu0():
    r, _ = run_cli(["--gpu-ids", "0,5"])
    assert r.returncode == 1
    assert "GPU 0" in r.stderr


def test_manifest_rejected_four_gpus():
    r, _ = run_cli(["--gpu-ids", "1,2,3,4"])
    assert r.returncode == 1
    assert "> 3" in r.stderr


def test_manifest_rejected_missing_manifest_sha():
    r, _ = run_cli(["--dataset-manifest-sha", ""])
    assert r.returncode == 1
    assert "dataset_manifest_sha256" in r.stderr


def test_config_templates_parse():
    """All engineering config templates are valid YAML with mandatory blocks."""
    cfg_dir = os.path.join(ENGINEERING, "configs")
    names = ["common_template.yaml", "classical_template.yaml", "unet_template.yaml",
             "deeplabv3plus_template.yaml", "segformer_b0_template.yaml",
             "segformer_b2_template.yaml", "fm_adapter_template.yaml"]
    for n in names:
        with open(os.path.join(cfg_dir, n)) as f:
            cfg = yaml.safe_load(f)
        assert cfg, f"{n} parsed empty"
    common = yaml.safe_load(open(os.path.join(cfg_dir, "common_template.yaml")))
    for block in ("data", "training", "evaluation", "resources", "provenance"):
        assert block in common, f"common template missing {block}"
    ev = common["evaluation"]
    assert ev["bootstrap"]["clusters"] == "cell"
    assert ev["bootstrap"]["n_boot"] == 2000 and ev["bootstrap"]["seed"] == 2026
