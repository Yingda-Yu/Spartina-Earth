"""Integrity tests for the M2.4 external-label intake artifacts.

Covers the canonical registry v1, the domain-overlap manifest produced by
scripts/data/labels/audit_label_domain_overlap.py, and the two family
passports. These are stdlib-only tests: they verify structure, tokens and
cross-file consistency, never the geospatial facts themselves (those were
computed in the gitignored work/intake environment).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = (
    REPO_ROOT / "datasets" / "manifests" / "china_external_label_registry_v1.csv"
)
V0_REGISTRY = (
    REPO_ROOT / "datasets" / "manifests" / "china_spartina_label_products_v0.csv"
)
OVERLAP = REPO_ROOT / "datasets" / "manifests" / "china_label_domain_overlap_v1.csv"
GEODATA_PASSPORT = (
    REPO_ROOT / "docs" / "audit" / "source_passports" / "geodata_family_2026-10_intake.json"
)
CMSA_PASSPORT = (
    REPO_ROOT / "docs" / "audit" / "source_passports" / "cmsa_family_2026-10_intake.json"
)
GOLD_PROTOCOL = REPO_ROOT / "docs" / "data" / "SPARTINA_GOLDSET_PROTOCOL.md"

REQUIRED_COLUMNS = {
    "product_id", "family", "year", "acquisition_status", "provenance_status",
    "semantic_status", "license", "analysis_allowed", "internal_training_allowed",
    "validation_allowed", "label_tier", "gold_use", "doi", "cstr",
    "archive_size_bytes", "archive_sha256", "passport", "supersedes",
    "measured_area_km2",
}
ALLOWED_ACQUISITION = {"ACQUIRED", "DOWNLOADED"}
ALLOWED_PROVENANCE = {
    "VERIFIED", "VERIFIED_BYTE_IDENTICAL_LOCAL", "CONFLICT_PORTAL_METADATA",
}
FAMILIES = {"GEODATA", "CMSA", "CM-SSM"}


@pytest.fixture(scope="module")
def registry() -> list[dict[str, str]]:
    with REGISTRY.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def v0_ids() -> set[str]:
    with V0_REGISTRY.open(encoding="utf-8", newline="") as handle:
        return {row["product_id"] for row in csv.DictReader(handle)}


def test_registry_shape_and_identity(registry: list[dict[str, str]]) -> None:
    assert len(registry) == 10
    assert REQUIRED_COLUMNS.issubset(registry[0])
    ids = [row["product_id"] for row in registry]
    assert len(set(ids)) == 10
    assert {row["family"] for row in registry} == FAMILIES
    years = {(row["family"], row["year"]) for row in registry}
    for year in ("1990", "2000", "2015", "2020"):
        assert ("GEODATA", year) in years
    for year in ("2017", "2018", "2019", "2020", "2021"):
        assert ("CMSA", year) in years
    assert ("CM-SSM", "2020") in years


def test_registry_status_tokens(registry: list[dict[str, str]]) -> None:
    for row in registry:
        assert row["acquisition_status"] in ALLOWED_ACQUISITION
        assert row["provenance_status"] in ALLOWED_PROVENANCE
        assert row["semantic_status"].startswith("VERIFIED_SPARTINA")
        assert row["analysis_allowed"] == "TRUE"
        assert row["validation_allowed"] == "TRUE_AS_EXTERNAL_REFERENCE"
        assert row["internal_training_allowed"] == "NO_REFERENCE_ONLY"
    assert sum(row["acquisition_status"] == "ACQUIRED" for row in registry) == 9
    assert {
        row["product_id"]: row["provenance_status"] for row in registry
    }["GEODATA-SPARTINA-2020-30M"] == "CONFLICT_PORTAL_METADATA"


def test_registry_is_silver_never_gold(registry: list[dict[str, str]]) -> None:
    assert {row["label_tier"] for row in registry} == {"SILVER"}
    assert {row["gold_use"].upper() for row in registry} == {"FALSE"}


def test_registry_hashes_and_passports(registry: list[dict[str, str]]) -> None:
    for row in registry:
        assert len(row["archive_sha256"]) == 64
        assert all(c in "0123456789abcdef" for c in row["archive_sha256"])
        int(row["archive_size_bytes"])
        passport = REPO_ROOT / row["passport"]
        assert passport.is_file(), passport
        assert row["doi"] and row["cstr"]


def test_registry_supersedes_v0(
    registry: list[dict[str, str]], v0_ids: set[str]
) -> None:
    for row in registry:
        assert row["supersedes"] in v0_ids
        assert row["supersedes"] == row["product_id"]


def test_license_classification(registry: list[dict[str, str]]) -> None:
    licenses = {row["product_id"]: row["license"] for row in registry}
    for pid in (
        "GEODATA-SPARTINA-1990", "GEODATA-SPARTINA-2000",
        "GEODATA-SPARTINA-2015", "GEODATA-SPARTINA-2020-30M",
    ):
        assert "RESTRICTED_RESEARCH_ONLY" in licenses[pid]
    for year in ("2017", "2018", "2019", "2020", "2021"):
        assert "CC-BY-NC-4.0" in licenses[f"NESDC-CMSA-{year}"]
    assert "SOURCE_LICENSE_CONFLICT" in licenses["ZENODO-CM-SSM-2020"]


def overlap_key(product_id: str) -> str:
    if product_id.startswith("GEODATA-SPARTINA-2020"):
        return "GEODATA_2020"
    if product_id.startswith("GEODATA-SPARTINA-"):
        return "GEODATA_" + product_id.rsplit("-", 1)[-1]
    if product_id.startswith("NESDC-CMSA-"):
        return "CMSA_" + product_id.rsplit("-", 1)[-1]
    assert product_id == "ZENODO-CM-SSM-2020"
    return "CM_SSM_2020"


def test_overlap_manifest_consistency(registry: list[dict[str, str]]) -> None:
    with OVERLAP.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    products = {r["product"] for r in rows}
    assert products == {overlap_key(r["product_id"]) for r in registry}
    assert {r["membership_bucket"] for r in rows} == {
        "KEEP", "EXCLUDE", "PROVISIONAL", "OUTSIDE_GRID",
    }
    buckets = {(r["product"], r["membership_bucket"]): float(r["mapped_area_km2"])
               for r in rows}
    # No external product lands in EXCLUDE cells.
    assert all(v == 0.0 for (_, bucket), v in buckets.items() if bucket == "EXCLUDE")
    for row in registry:
        total = float(str(row["measured_area_km2"]).split()[0])
        key = overlap_key(row["product_id"])
        inside = sum(buckets[(key, b)]
                     for b in ("KEEP", "PROVISIONAL", "OUTSIDE_GRID"))
        # Raster products reconcile exactly (pixel-count rounding); vector
        # products lose <0.5% to the make-valid/exact-intersection pipeline
        # documented in the overlap audit.
        tolerance = max(0.02, 0.005 * total)
        assert 0.0 <= inside <= total + tolerance, (key, inside, total)
        assert total - inside <= tolerance, (key, inside, total)


def test_geodata_passport() -> None:
    doc = json.loads(GEODATA_PASSPORT.read_text(encoding="utf-8"))
    products = {p["product_id"]: p for p in doc["products"]}
    assert set(products) == {
        "GEODATA-SPARTINA-1990", "GEODATA-SPARTINA-2000",
        "GEODATA-SPARTINA-2015", "GEODATA-SPARTINA-2020-30M",
    }
    assert products["GEODATA-SPARTINA-2015"]["local_byte_identity"].startswith(
        "Extracted TIF sha256"
    )
    resolution = products["GEODATA-SPARTINA-2020-30M"]["contradiction_resolution"]
    assert resolution["verdict"] == "DELIVERED_BYTES_VERIFIED_SPARTINA; PORTAL_ABSTRACT_CONFLICT"
    assert doc["usage_policy"]["gold_use"] is False
    assert doc["grid_alignment"]["verdict"].startswith("NOT_DIRECTLY_COMPARABLE")
    assert doc["provider"]["license_classification"] == "RESTRICTED_RESEARCH_ONLY"


def test_cmsa_passport() -> None:
    doc = json.loads(CMSA_PASSPORT.read_text(encoding="utf-8"))
    years = {item["year"]: item for item in doc["per_year_facts"]}
    assert sorted(years) == [2017, 2018, 2019, 2020, 2021]
    assert [years[y]["positive_gridcode2_area_km2"] for y in sorted(years)] == [
        494.69, 504.31, 532.99, 571.35, 586.51,
    ]
    assert doc["archive"]["size_bytes"] == 6455174
    assert doc["usage_policy"]["gold_use"] is False
    assert doc["usage_policy"]["tier"] == "SILVER"
    assert doc["gridcode_zero_semantics"].startswith("UNKNOWN")


def test_goldset_protocol_guard_present() -> None:
    text = GOLD_PROTOCOL.read_text(encoding="utf-8")
    assert "gold_use=FALSE" in text
    assert "GOLD count remains **0**" in text
    for name in ("GEODATA", "CMSA"):
        assert name in text
