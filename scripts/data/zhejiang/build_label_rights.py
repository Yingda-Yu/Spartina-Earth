#!/usr/bin/env python3
"""Write the label rights matrix manifest (M2.1a2, Issue #12).

Static, evidence-backed rows from ``spartina.data.zhejiang.rights``; no
network access. Emits CSV + parquet and a one-line registry fingerprint
sidecar so downstream manifests can reference the exact matrix version.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from spartina.data.zhejiang.rights import (  # noqa: E402
    LABEL_RIGHTS_COLUMNS,
    label_rights_records,
    rights_registry_fingerprint,
)


def main() -> int:
    rows = label_rights_records()
    mdir = REPO_ROOT / "datasets/manifests"
    df = pd.DataFrame(rows, columns=list(LABEL_RIGHTS_COLUMNS))
    csv_path = mdir / "zhejiang_label_rights_v0.csv"
    df.to_csv(csv_path, index=False)
    df.to_parquet(mdir / "zhejiang_label_rights_v0.parquet", index=False)

    fp = rights_registry_fingerprint(rows)
    sidecar = {
        "manifest": "zhejiang_label_rights_v0",
        "n_assets": len(rows),
        "registry_fingerprint": fp,
        "columns": list(LABEL_RIGHTS_COLUMNS),
    }
    (mdir / "zhejiang_label_rights_v0.fingerprint.json").write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"rights rows={len(rows)} registry_fingerprint={fp}")
    print(f"-> {csv_path.relative_to(REPO_ROOT)} (+ parquet, fingerprint)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
