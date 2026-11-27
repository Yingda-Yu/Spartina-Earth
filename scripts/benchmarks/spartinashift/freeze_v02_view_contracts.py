#!/usr/bin/env python3
"""Issue #21, Phase F -- freeze SINGLE_EVENT_CANONICAL / MULTI_DATE_SEASONAL.

The two view contracts are frozen BEFORE training on data semantics
alone, and bind the Phase A requirements checksum. Output:

  benchmarks/spartinashift/v0_2/V0_2_VIEW_CONTRACTS.json

Immutability mirrors the other v0.2 freezes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

from spartina.benchmark.v02 import views as V  # noqa: E402

V02_DIR = REPO_ROOT / "benchmarks/spartinashift/v0_2"
REQUIREMENTS_JSON = V02_DIR / "SPARTINASHIFT_V0_2_SUPPORT_REQUIREMENTS.json"
OUT_JSON = V02_DIR / "V0_2_VIEW_CONTRACTS.json"


def main() -> int:
    requirements = json.loads(REQUIREMENTS_JSON.read_text("utf-8"))
    req_checksum = str(requirements["checksum"])

    document = V.build_view_contracts(req_checksum)
    document["phase"] = "F"
    document["generated_utc"] = datetime.now(UTC).isoformat()
    document["git_commit"] = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, check=True,
        capture_output=True, text=True).stdout.strip()
    document["document_checksum"] = V.document_checksum(document)
    V.validate_view_contracts(document)

    if OUT_JSON.exists():
        old = json.loads(OUT_JSON.read_text("utf-8"))
        if old.get("document_checksum") != document["document_checksum"]:
            raise SystemExit(
                "REFUSING TO MUTATE FROZEN VIEW CONTRACTS: existing "
                "freeze differs; bump the version instead.")
        print("frozen view contracts already present and identical")
    else:
        OUT_JSON.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"wrote {OUT_JSON}")
    print(f"checksum: {document['document_checksum']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
