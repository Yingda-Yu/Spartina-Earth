"""Split validator tests on synthetic geometry (SPLIT_DESIGN_AND_LEAKAGE_AUDIT.md).

Uses the real checker (src/spartina/evaluation/splits.py) through the
validator CLI with synthetic non-overlapping cells. No real split exists
yet (freeze is gated), so these are machinery tests only.
Run: pytest engineering/tests/test_validate_splits.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCRIPT = os.path.join(ROOT, "engineering", "dataset_validation", "validate_splits.py")


def make_manifest(tmp, cells, reserve=None, buffer_m=250):
    split = {
        "split_id": "SPLIT_TEST_SYNTHETIC",
        "cells": cells,
        "buffer_m": buffer_m,
    }
    p = os.path.join(tmp, "split.json")
    json.dump(split, open(p, "w"))
    return p


def make_geometry(tmp, rects):
    features = []
    for cid, (xmin, ymin, xmax, ymax) in rects.items():
        features.append({
            "type": "Feature",
            "properties": {"cell_id": cid},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[xmin, ymin], [xmax, ymin],
                                          [xmax, ymax], [xmin, ymax],
                                          [xmin, ymin]]]},
        })
    p = os.path.join(tmp, "cells.geojson")
    json.dump({"type": "FeatureCollection", "features": features}, open(p, "w"))
    return p


def run(manifest, geometry=None, reserve=None):
    cmd = [sys.executable, SCRIPT, "--split-manifest", manifest]
    if geometry:
        cmd += ["--geometry-json", geometry]
    if reserve:
        cmd += ["--reserve", reserve]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


def test_disjoint_split_passes():
    # three cells spaced 5000 m apart, 1000 m wide -> gaps far beyond 250 m
    rects = {
        "A": (0, 0, 1000, 1000),
        "B": (6000, 0, 7000, 1000),
        "C": (12000, 0, 13000, 1000),
    }
    with tempfile.TemporaryDirectory() as tmp:
        m = make_manifest(tmp, {"train": ["A"], "validation": ["B"], "test": ["C"]})
        g = make_geometry(tmp, rects)
        r = run(m, geometry=g)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PASS" in r.stdout


def test_leaky_split_fails():
    # B and C adjacent (touching) in different roles -> buffer violation
    rects = {
        "A": (0, 0, 1000, 1000),
        "B": (2000, 0, 3000, 1000),
        "C": (3000, 0, 4000, 1000),  # touches B exactly -> gap 0 <= 250
    }
    with tempfile.TemporaryDirectory() as tmp:
        m = make_manifest(tmp, {"train": ["A", "B"], "test": ["C"]})
        g = make_geometry(tmp, rects)
        r = run(m, geometry=g)
        assert r.returncode == 1
        assert "A2" in r.stdout


def test_duplicate_role_fails():
    with tempfile.TemporaryDirectory() as tmp:
        m = make_manifest(tmp, {"train": ["A"], "validation": ["A", "B"], "test": []})
        r = run(m)
        assert r.returncode == 1
        assert "A1" in r.stdout


def test_reserve_violation_fails():
    with tempfile.TemporaryDirectory() as tmp:
        m = make_manifest(tmp, {"train": ["A"], "validation": [], "test": ["R1"]})
        rfile = os.path.join(tmp, "reserve.txt")
        open(rfile, "w").write("R1\nR2\n")
        r = run(m, reserve=rfile)
        assert r.returncode == 1
        assert "A5" in r.stdout


def test_temporal_grouping_check():
    # manifest with per-cell dates must pass when roles are cell-keyed
    with tempfile.TemporaryDirectory() as tmp:
        split = {
            "split_id": "SPLIT_TEST_DATES",
            "cells": {"train": ["A"], "test": ["B"]},
            "unit_dates": {"A": ["2020-06-01", "2020-07-01"],
                           "B": ["2020-06-03", "2021-05-02"]},
        }
        m = os.path.join(tmp, "split.json")
        json.dump(split, open(m, "w"))
        g = make_geometry(tmp, {"A": (0, 0, 1000, 1000),
                                "B": (6000, 0, 7000, 1000)})
        r = run(m, geometry=g)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "A3" in r.stdout
