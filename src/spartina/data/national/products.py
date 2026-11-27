"""National Spartina label-product family registry (Issue #14).

Loads ``datasets/manifests/china_spartina_label_products_v0.csv`` and
enforces the instruction section 17 field contract.  Only verified
rows are written to that file; products not yet obtained carry
explicit access statuses instead of fabricated metadata.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Final, get_type_hints

LABEL_PRODUCT_MANIFEST: Final[Path] = Path(
    "datasets/manifests/china_spartina_label_products_v0.csv"
)

# Required columns (instruction section 17), in stable order.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "product_id",
    "year",
    "temporal_semantics",
    "resolution",
    "domain",
    "format",
    "projection",
    "source_imagery",
    "classification_method",
    "training_reference_method",
    "reported_accuracy",
    "mapped_area",
    "feature_count",
    "doi",
    "cstr",
    "publisher",
    "license",
    "scientific_analysis_allowed",
    "internal_training_allowed",
    "validation_allowed",
    "redistribution_allowed",
    "derived_model_release_status",
    "local_copy_status",
    "sha256",
    "provenance_status",
    "access_status",
    "size_bytes",
    "evidence_url",
    "notes",
)


class AccessStatus(str, Enum):
    """How the product bytes can currently be obtained."""

    DOWNLOADED = "DOWNLOADED"
    LOCAL_COPY_PRESENT = "LOCAL_COPY_PRESENT"
    OPEN_WITH_PURPOSE_REGISTRATION = "OPEN_WITH_PURPOSE_REGISTRATION"
    BLOCKED_BY_ORDER = "BLOCKED_BY_ORDER"
    BLOCKED_BY_ACCOUNT = "BLOCKED_BY_ACCOUNT"
    NOT_FOUND = "NOT_FOUND"
    EXISTS_WITH_METADATA_CONTRADICTION = "EXISTS_WITH_METADATA_CONTRADICTION"


class ProvenanceStatus(str, Enum):
    """Local-copy provenance verdicts."""

    VERIFIED_OFFICIAL_ARCHIVE = "VERIFIED_OFFICIAL_ARCHIVE"
    VERIFIED_CM_SSM_2020 = "VERIFIED_CM_SSM_2020"
    DERIVED_VARIANT = "DERIVED_VARIANT"
    RELATIONSHIP_UNKNOWN = "RELATIONSHIP_UNKNOWN"
    PORTAL_METADATA_ONLY = "PORTAL_METADATA_ONLY"
    UNAUDITED = "UNAUDITED"


class LicenseDecision(str, Enum):
    """Rights verdicts; the conservative stance is explicit."""

    CC_BY_4_0 = "CC_BY_4_0"
    CC_BY_NC_4_0 = "CC_BY_NC_4_0"
    PORTAL_PLATFORM_TERMS_ONLY = "PORTAL_PLATFORM_TERMS_ONLY"
    SOURCE_LICENSE_CONFLICT = "SOURCE_LICENSE_CONFLICT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LabelProduct:
    """One row of the national label-product matrix."""

    product_id: str
    year: str
    temporal_semantics: str
    resolution: str
    domain: str
    format: str
    projection: str
    source_imagery: str
    classification_method: str
    training_reference_method: str
    reported_accuracy: str
    mapped_area: str
    feature_count: str
    doi: str
    cstr: str
    publisher: str
    license: str
    scientific_analysis_allowed: str
    internal_training_allowed: str
    validation_allowed: str
    redistribution_allowed: str
    derived_model_release_status: str
    local_copy_status: str
    sha256: str
    provenance_status: str
    access_status: str
    size_bytes: str
    evidence_url: str
    notes: str

    @property
    def year_int(self) -> int | None:
        try:
            return int(self.year)
        except ValueError:
            return None


@dataclass(frozen=True)
class LabelProductRegistry:
    """Validated in-memory label-product matrix."""

    products: tuple[LabelProduct, ...] = field(default_factory=tuple)

    def by_id(self, product_id: str) -> LabelProduct:
        for product in self.products:
            if product.product_id == product_id:
                return product
        raise KeyError(product_id)

    def years(self) -> list[str]:
        return sorted({p.year for p in self.products})


def _truthy_csv(row: dict[str, str], column: str) -> str:
    value = row.get(column, "").strip()
    upper = value.upper()
    if upper in {"TRUE", "YES", "1"}:
        return "TRUE"
    if upper in {"FALSE", "NO", "0"}:
        return "FALSE"
    return value or "UNKNOWN"


def load_label_products(
    manifest: Path | str = LABEL_PRODUCT_MANIFEST,
) -> LabelProductRegistry:
    """Read and validate the national label-product matrix."""
    path = Path(manifest)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"empty manifest: {path}")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        extra = [c for c in reader.fieldnames if c not in REQUIRED_COLUMNS]
        if missing or extra:
            raise ValueError(
                f"manifest column mismatch in {path}: "
                f"missing={missing} extra={extra}"
            )
        rows: list[LabelProduct] = []
        seen: set[str] = set()
        hints = get_type_hints(LabelProduct)
        for line, raw in enumerate(reader, start=2):
            if not raw.get("product_id"):
                raise ValueError(f"{path}:{line}: missing product_id")
            if raw["product_id"] in seen:
                raise ValueError(
                    f"{path}:{line}: duplicate product_id {raw['product_id']}"
                )
            seen.add(raw["product_id"])
            for column in REQUIRED_COLUMNS:
                expected = hints[column]
                value = raw.get(column, "")
                if expected is str and value is None:
                    raise ValueError(f"{path}:{line}: {column} is null")
            rows.append(LabelProduct(**{c: (raw.get(c, "") or "") for c in REQUIRED_COLUMNS}))
    return LabelProductRegistry(tuple(rows))
