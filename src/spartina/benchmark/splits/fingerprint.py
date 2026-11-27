"""Logical fingerprints for deterministic split generation.

Parquet/CSV container bytes can differ (encoders embed timestamps); the
*scientific content* is what must reproduce. The fingerprint covers a
fixed, ordered projection of the window records plus the split config,
canonicalised JSON with sorted keys.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Fields whose values define the logical split. Generation timestamps,
# file paths of containers and git metadata are deliberately excluded.
MANIFEST_FINGERPRINT_FIELDS = (
    "tile_id",
    "row_off",
    "col_off",
    "height",
    "width",
    "split",
    "eligible_for_train",
    "eligible_for_eval",
    "exclusion_reason",
    "silver_positive_pixels",
    "silver_eval_pixels",
    "weak_positive_pixels",
    "weak_eval_pixels",
    "ignore_pixels",
    "weak_only_candidate_pixels",
    "silver_component_ids",
    "weak_candidate_component_ids",
    "source_stack_checksum",
)


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def logical_manifest_fingerprint(
    records: list[dict[str, Any]],
) -> str:
    """Stable sha256 of the logical tile manifest content."""
    projected = [
        {k: r.get(k) for k in MANIFEST_FINGERPRINT_FIELDS}
        for r in sorted(records, key=lambda r: r["tile_id"])
    ]
    return hashlib.sha256(_canonical(projected).encode("utf-8")).hexdigest()


def split_config_fingerprint(config: dict[str, Any]) -> str:
    """Stable sha256 of the split configuration."""
    return hashlib.sha256(_canonical(config).encode("utf-8")).hexdigest()
