"""Cell evidence strata for the national coastal domain (Issue #16).

Every domain cell carries two *independent* descriptions:

1. orthogonal boolean evidence flags (a cell may carry several);
2. exactly one exclusive priority stratum, partitioning the full domain.

The exclusive taxonomy is a strict priority ladder (the first matching
evidence level wins) so that the per-cell stratum counts always sum to
the domain size:

``GOLD_EVIDENCE`` > ``MULTI_PRODUCT_SILVER_POSITIVE`` >
``SILVER_2015_POSITIVE_ONLY`` > ``CMSSM_2020_POSITIVE_ONLY`` >
``NEAR_SILVER_UNLABELED`` > ``UNLABELED_COASTAL``.

``UNLABELED_*`` means *absence of evidence in obtained products*; it is
never an ecological negative. CMSA history, management geometry and
GOLD layers are ``DESIGNED_NOT_BUILD`` at v0: their flags exist in the
schema but are empty sets.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

# Exclusive priority strata (highest priority first).
GOLD_EVIDENCE = "GOLD_EVIDENCE"
MULTI_PRODUCT_SILVER_POSITIVE = "MULTI_PRODUCT_SILVER_POSITIVE"
SILVER_2015_POSITIVE_ONLY = "SILVER_2015_POSITIVE_ONLY"
CMSSM_2020_POSITIVE_ONLY = "CMSSM_2020_POSITIVE_ONLY"
NEAR_SILVER_UNLABELED = "NEAR_SILVER_UNLABELED"
UNLABELED_COASTAL = "UNLABELED_COASTAL"

PRIORITY_STRATA: tuple[str, ...] = (
    GOLD_EVIDENCE,
    MULTI_PRODUCT_SILVER_POSITIVE,
    SILVER_2015_POSITIVE_ONLY,
    CMSSM_2020_POSITIVE_ONLY,
    NEAR_SILVER_UNLABELED,
    UNLABELED_COASTAL,
)

# Orthogonal boolean flags written to the strata table.
BOOLEAN_FLAGS: tuple[str, ...] = (
    "gold_evidence",
    "silver_2015_positive",
    "cmssm_2020_positive",
    "silver_2015_nearby",
    "multi_product_positive",
    "cmsa_positive_history",
    "management_evidence_available",
)

# Flags kept in the schema but not populated at v0 (evidence not obtained).
DESIGNED_NOT_BUILD_FLAGS: tuple[str, ...] = (
    "gold_evidence",
    "cmsa_positive_history",
    "management_evidence_available",
)


def assign_priority_stratum(
    *,
    silver_2015_positive: bool,
    cmssm_2020_positive: bool,
    silver_2015_nearby: bool,
    gold_evidence: bool = False,
) -> str:
    """Return the unique exclusive stratum for one cell.

    ``silver_2015_nearby`` is the fixed one-lattice-ring dilation of
    2015-positive cells and is evaluated only after all positive layers.
    """
    if gold_evidence:
        return GOLD_EVIDENCE
    if silver_2015_positive and cmssm_2020_positive:
        return MULTI_PRODUCT_SILVER_POSITIVE
    if silver_2015_positive:
        return SILVER_2015_POSITIVE_ONLY
    if cmssm_2020_positive:
        return CMSSM_2020_POSITIVE_ONLY
    if silver_2015_nearby:
        return NEAR_SILVER_UNLABELED
    return UNLABELED_COASTAL


def stratum_counts(
    strata: Iterable[str],
) -> dict[str, int]:
    """Count occurrences of every priority stratum (zero-filled)."""
    counter = Counter(strata)
    unknown = set(counter) - set(PRIORITY_STRATA)
    if unknown:
        raise ValueError(f"unknown strata labels: {sorted(unknown)}")
    return {name: counter.get(name, 0) for name in PRIORITY_STRATA}


def assert_partition(
    rows: Iterable[Mapping[str, object]],
    *,
    expected_cells: int | None = None,
) -> dict[str, int]:
    """Validate strata rows: boolean flags, one stratum each, sum equals N."""
    rows = list(rows)
    labels: list[str] = []
    for row in rows:
        for flag in BOOLEAN_FLAGS:
            if flag not in row:
                raise ValueError(f"row missing boolean flag {flag!r}: {row!r}")
            value = row[flag]
            if not isinstance(value, bool | int) or value not in (0, 1):
                raise ValueError(f"flag {flag!r} not boolean: {row!r}")
        label = row.get("exclusive_stratum")
        if not isinstance(label, str):
            raise ValueError(f"row missing string exclusive_stratum: {row!r}")
        recomputed = assign_priority_stratum(
            silver_2015_positive=bool(row["silver_2015_positive"]),
            cmssm_2020_positive=bool(row["cmssm_2020_positive"]),
            silver_2015_nearby=bool(row["silver_2015_nearby"]),
            gold_evidence=bool(row["gold_evidence"]),
        )
        if label != recomputed:
            raise ValueError(
                f"stratum {label!r} inconsistent with flags "
                f"(expected {recomputed!r}): {row!r}"
            )
        labels.append(label)
    counts = stratum_counts(labels)
    if expected_cells is not None and sum(counts.values()) != expected_cells:
        raise ValueError(
            f"partition size {sum(counts.values())} != expected {expected_cells}"
        )
    return counts
