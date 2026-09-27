#!/usr/bin/env python
"""Compute frozen train-only normalization statistics for Pilot-0.

Runs once, before any model work. Aborts if a normalization file with a
different checksum already exists. TEST is never read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from spartina.data.normalization import (  # noqa: E402
    compute_band_stats,
    normalization_payload,
    payload_checksum,
    write_normalization,
)
from spartina.data.pilot0 import load_sources, train_unique_pixel_mask  # noqa: E402
from spartina.experiments.runner import (  # noqa: E402
    load_common,
    repo_root,
    split_fingerprint_of,
    split_registry,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=repo_root())
    args = ap.parse_args()
    common = load_common(args.repo)
    sources = load_sources(args.repo, common)
    sfp = split_fingerprint_of(split_registry(args.repo, common))
    train_mask = train_unique_pixel_mask(sources)
    stats = compute_band_stats(
        sources.stack, train_mask,
        float(common["normalization"]["low_pct"]),
        float(common["normalization"]["high_pct"]))
    payload = normalization_payload(
        stats, sources.stack_checksum, sfp, int(train_mask.sum()), common)
    payload["checksum"] = payload_checksum(payload)
    out = args.repo / common["paths"]["normalization"]
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing {out}")
    digest = write_normalization(payload, out)
    print(f"normalization written: {out}")
    print(f"sha256: {digest}")
    print(f"train unique pixels: {int(train_mask.sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
