"""Label-quality tiers used across manifests and benchmark documentation.

Definitions (see ``docs/audit/LABEL_INVENTORY.md``):

GOLD       field / UAV / expert-verified high-quality labels.
SILVER     credible government or peer-reviewed mapping products with known
           provenance.
WEAK       index/rule/legacy automatic labels.
UNLABELED  raw EO observations for self-supervised pretraining.
"""

from __future__ import annotations

from enum import Enum


class LabelQuality(str, Enum):
    """Closed vocabulary for the ``label_quality`` manifest field."""

    GOLD = "GOLD"
    SILVER = "SILVER"
    WEAK = "WEAK"
    UNLABELED = "UNLABELED"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Return all tier strings (used by schema validation and tests)."""
        return tuple(member.value for member in cls)


__all__ = ["LabelQuality"]
