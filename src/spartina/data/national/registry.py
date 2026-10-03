"""Multimodal national source registry (Issue #14, sections 30-36).

Roles follow the instruction vocabulary::

    CORE / OPTIONAL / OPTIONAL_CONTEXT / VALIDATION_ONLY / BLOCKED

The registry itself is
``datasets/manifests/china_multimodal_sources_v0.csv``; only verified
metadata rows live there, and access blockers (login/order/license)
are explicit rather than bypassed.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final

MULTIMODAL_MANIFEST: Final[Path] = Path(
    "datasets/manifests/china_multimodal_sources_v0.csv"
)

COLUMNS: Final[tuple[str, ...]] = (
    "dataset_id",
    "family",
    "role",
    "provider",
    "title",
    "temporal_coverage",
    "native_resolution",
    "gee_asset",
    "doi",
    "url",
    "license",
    "access_status",
    "local_copy",
    "passport_path",
    "purpose",
    "notes",
)


class Role(str, Enum):
    CORE = "CORE"
    OPTIONAL = "OPTIONAL"
    OPTIONAL_CONTEXT = "OPTIONAL_CONTEXT"
    VALIDATION_ONLY = "VALIDATION_ONLY"
    BLOCKED = "BLOCKED"


class AccessStatus(str, Enum):
    GEE_ASSET = "GEE_ASSET"
    PUBLIC_DIRECT = "PUBLIC_DIRECT"
    REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED"
    ORDER_REQUIRED = "ORDER_REQUIRED"
    LICENSE_GATED = "LICENSE_GATED"
    METADATA_ONLY = "METADATA_ONLY"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class MultimodalSource:
    dataset_id: str
    family: str
    role: Role
    provider: str
    title: str
    temporal_coverage: str
    native_resolution: str
    gee_asset: str
    doi: str
    url: str
    license: str
    access_status: AccessStatus
    local_copy: str
    passport_path: str
    purpose: str
    notes: str = ""


@dataclass(frozen=True)
class MultimodalRegistry:
    sources: tuple[MultimodalSource, ...] = field(default_factory=tuple)

    def by_family(self) -> dict[str, list[MultimodalSource]]:
        grouped: dict[str, list[MultimodalSource]] = {}
        for source in self.sources:
            grouped.setdefault(source.family, []).append(source)
        return grouped

    def by_id(self, dataset_id: str) -> MultimodalSource:
        for source in self.sources:
            if source.dataset_id == dataset_id:
                return source
        raise KeyError(dataset_id)


def load_multimodal_registry(
    manifest: Path | str = MULTIMODAL_MANIFEST,
) -> MultimodalRegistry:
    """Read and validate the multimodal source registry."""
    path = Path(manifest)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"empty registry: {path}")
        if tuple(reader.fieldnames) != COLUMNS:
            raise ValueError(
                f"registry column mismatch in {path}: "
                f"{reader.fieldnames} != {COLUMNS}"
            )
        sources: list[MultimodalSource] = []
        seen: set[str] = set()
        for line, raw in enumerate(reader, start=2):
            if not raw.get("dataset_id"):
                raise ValueError(f"{path}:{line}: missing dataset_id")
            if raw["dataset_id"] in seen:
                raise ValueError(f"{path}:{line}: duplicate {raw['dataset_id']}")
            seen.add(raw["dataset_id"])
            role = Role(raw["role"])
            access = AccessStatus(raw["access_status"])
            sources.append(
                MultimodalSource(
                    role=role,
                    access_status=access,
                    **{k: raw[k] for k in COLUMNS if k not in ("role", "access_status")},
                )
            )
    return MultimodalRegistry(tuple(sources))
